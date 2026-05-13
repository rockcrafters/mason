"""pytest plugin: tests marked @pytest.mark.scored return float in [0,1].

unmarked tests: pass -> 1.0, fail -> 0.0 in summary report.
marked tests must return float in [0,1] or pytest errors.
final terminal summary renders pivoted bar chart (one column per model)
plus per-axis group averages and a separate compliance-gate pass-rate.
"""
from __future__ import annotations

import json
import math
import shutil
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from _pytest.config import Config
    from _pytest.nodes import Item
    from _pytest.reports import TestReport
    from _pytest.terminal import TerminalReporter


def scored(func=None, *, short_slug: str | None = None):
    """Decorator alias -- `@scored` or `@scored(short_slug="x")`.

    `short_slug` overrides the test function name in the summary row label
    (the bracketed param section is preserved).
    """
    if func is None:
        def deco(f):
            return pytest.mark.scored(short_slug=short_slug)(f)
        return deco
    return pytest.mark.scored(func)


def gate(func):
    """Mark a scored test as a compliance gate (pass/fail, not quality signal).

    Gates are boolean-ish: they hit ~1.0 on any valid output and exist to flag
    catastrophic failures (unparseable yaml, wrong schema version usage, ...).
    They are excluded from the quality avg and reported as a separate pass-rate
    so they don't inflate the headline score.
    """
    return pytest.mark.gate(pytest.mark.scored(func))


_SCORE_KEY = pytest.StashKey[float]()
_PARAMS_KEY = pytest.StashKey[dict[str, str]]()
_BAR_WIDTH_DEFAULT = 10


@dataclass(frozen=True)
class _Row:
    nodeid: str
    score: float
    params: dict[str, str]
    scored: bool
    gate: bool = False
    slug: str | None = None
    duration: float = 0.0


_RESULTS_KEY: pytest.StashKey[list[_Row]] = pytest.StashKey()
_SKIP_COUNTS_KEY: pytest.StashKey[dict[str, int]] = pytest.StashKey()


def pytest_configure(config: "Config") -> None:
    config.addinivalue_line(
        "markers",
        "scored: test returns float in [0,1] instead of asserting",
    )
    config.addinivalue_line(
        "markers",
        "gate: scored test acting as a compliance gate; excluded from quality avg",
    )
    config.stash[_RESULTS_KEY] = []
    config.stash[_SKIP_COUNTS_KEY] = {}


def pytest_addoption(parser: pytest.Parser) -> None:
    g = parser.getgroup("scored")
    g.addoption(
        "--scored-report",
        action="store",
        default=None,
        help="write per-test scores to json file at this path",
    )
    g.addoption(
        "--scored-bar-width",
        action="store",
        type=int,
        default=_BAR_WIDTH_DEFAULT,
        help="max width of ascii score bar (default 10; auto-shrinks to fit terminal)",
    )
    g.addoption(
        "--scored-min",
        action="store",
        type=float,
        default=None,
        help="fail suite if any group avg falls below this threshold",
    )
    g.addoption(
        "--scored-verbose",
        action="store_true",
        default=False,
        help="show all rows (do not collapse perfect rows in pivoted view)",
    )


def _param_label(value: Any) -> str:
    """Prefer .name / .id over repr for dataclass-like params."""
    for attr in ("name", "id"):
        v = getattr(value, attr, None)
        if isinstance(v, str):
            return v
    return str(value)


def _extract_params(item: "Item") -> dict[str, str]:
    callspec = getattr(item, "callspec", None)
    if callspec is None:
        return {}
    out: dict[str, str] = {}
    for k, v in callspec.params.items():
        # for compound params (e.g. Run w/ .case + .model), expand inners
        # and skip the wrapper to avoid noisy duplicate grouping axes.
        expanded = False
        for attr in ("case", "model"):
            inner = getattr(v, attr, None)
            if inner is not None:
                inner_label = _param_label(inner)
                if inner_label:
                    out[attr] = inner_label
                    expanded = True
        if not expanded:
            out[k] = _param_label(v)
    return out


def _is_scored(item: "Item") -> bool:
    return item.get_closest_marker("scored") is not None


def _is_gate(item: "Item") -> bool:
    return item.get_closest_marker("gate") is not None


def _slug_for(item: "Item") -> str | None:
    m = item.get_closest_marker("scored")
    if m is None:
        return None
    s = m.kwargs.get("short_slug")
    return s if isinstance(s, str) else None


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item: "Item"):
    if not _is_scored(item):
        yield
        return
    original = item.obj
    captured: dict[str, Any] = {}

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        captured["result"] = original(*args, **kwargs)
        return None

    item.obj = wrapper
    try:
        yield
    finally:
        item.obj = original

    if "result" not in captured:
        return
    score = captured["result"]
    if not isinstance(score, (int, float)) or isinstance(score, bool):
        raise pytest.UsageError(
            f"scored test {item.nodeid} must return float, got {type(score).__name__}"
        )
    score = float(score)
    if not math.isfinite(score) or score < 0.0 or score > 1.0:
        raise pytest.UsageError(
            f"scored test {item.nodeid} returned {score!r}; must be in [0,1]"
        )
    item.stash[_SCORE_KEY] = score
    item.stash[_PARAMS_KEY] = _extract_params(item)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: "Item", call):
    outcome = yield
    report: TestReport = outcome.get_result()
    if report.skipped:
        reason = getattr(report, "wasxfail", None) or ""
        if not reason:
            longrepr = report.longrepr
            reason = (
                str(longrepr[-1]) if isinstance(longrepr, tuple) else str(longrepr)
            ).strip()
        counts: dict[str, int] = item.config.stash[_SKIP_COUNTS_KEY]
        counts[reason] = counts.get(reason, 0) + 1
        return
    if report.when != "call":
        return
    scored = _is_scored(item)
    if scored:
        score = item.stash.get(_SCORE_KEY, None)
        if score is None:
            score = 0.0
        params = item.stash.get(_PARAMS_KEY, {})
    else:
        score = 1.0 if report.passed else 0.0
        params = _extract_params(item)
    # prefer agent run duration from a param with .duration_s (e.g. Run);
    # fall back to pytest's own execution time.
    run_dur: float | None = None
    callspec = getattr(item, "callspec", None)
    if callspec:
        for v in callspec.params.values():
            d = getattr(v, "duration_s", None)
            if isinstance(d, (int, float)) and not isinstance(d, bool):
                run_dur = float(d)
                break
    duration = run_dur if run_dur is not None else float(getattr(report, "duration", 0.0) or 0.0)
    rows: list[_Row] = item.config.stash[_RESULTS_KEY]
    rows.append(_Row(
        nodeid=report.nodeid, score=score, params=params,
        scored=scored, gate=_is_gate(item), slug=_slug_for(item),
        duration=duration,
    ))


_RED = "\033[31m"
_YELLOW = "\033[33m"
_GREEN = "\033[32m"
_DIM = "\033[2m"
_RESET = "\033[0m"


def _bar(score: float, width: int) -> str:
    filled = int(round(score * width))
    filled = max(0, min(width, filled))
    return "[" + "#" * filled + "-" * (width - filled) + "]"


def _color_for(score: float) -> str:
    if score < 0.5:
        return _RED
    if score < 0.8:
        return _YELLOW
    return _GREEN


def _cell_width(bar_w: int) -> int:
    # "0.00" (4) + " " (1) + "[...]" (bar_w + 2)
    return 4 + 1 + bar_w + 2


def _fmt_cell(score: float | None, bar_w: int, *, color: bool) -> str:
    w = _cell_width(bar_w)
    if score is None:
        text = "-".center(w)
        if color:
            return f"{_DIM}{text}{_RESET}"
        return text
    text = f"{score:4.2f} {_bar(score, bar_w)}"
    text = text.rjust(w)
    if color:
        return f"{_color_for(score)}{text}{_RESET}"
    return text


def _fmt_score_bar(score: float, width: int, *, color: bool, std: float | None = None) -> str:
    """Single-column formatter (used in axis avgs + overall)."""
    pm = f" (+/-{std:.2f})" if std is not None else ""
    text = f"{score:5.2f}{pm}  {_bar(score, width)}"
    if not color:
        return text
    return f"{_color_for(score)}{text}{_RESET}"


def _strip_file_prefix(nodeid: str) -> str:
    """`slice/test_x.py::test_y[...]` -> `test_y[...]`."""
    sep = nodeid.rfind("::")
    return nodeid[sep + 2:] if sep != -1 else nodeid


def _model_slug(model: str) -> tuple[str, str]:
    """Return (backend_slug, short_model_slug). Heuristic for now."""
    if model.startswith("claude-"):
        m = model[len("claude-"):]
        parts = m.rsplit("-", 1)
        # strip trailing date stamp YYYYMMDD
        if len(parts) == 2 and parts[1].isdigit() and len(parts[1]) == 8:
            m = parts[0]
        return "claude", m
    return "?", model


def _row_label(r: _Row) -> str:
    """Row key for pivot: drop file prefix, strip trailing model substring,
    drop a duplicate leading case value (e.g. `case-case-slice` -> `case-slice`),
    optionally swap test-func name for slug.
    """
    func = _strip_file_prefix(r.nodeid)
    br = func.find("[")
    if br == -1:
        return r.slug or func
    base = r.slug or func[:br]
    inner = func[br + 1 : func.rfind("]")]
    model = r.params.get("model")
    if model:
        # strip model substring (with adjacent separator) anywhere in inner
        for pat in (f"-{model}-", f"-{model}", f"{model}-", model):
            if pat in inner:
                inner = inner.replace(pat, "", 1)
                break
    case = r.params.get("case")
    if case and inner.startswith(f"{case}-{case}"):
        inner = inner[len(case) + 1:]  # drop one duplicate copy
    elif case and inner == case:
        # noop; keep as-is
        pass
    inner = inner.strip("-")
    if inner:
        return f"{base}[{inner}]"
    return base


def _group_averages(rows: list[_Row]) -> dict[str, dict[str, tuple[float, float, int]]]:
    keys: set[str] = set()
    for r in rows:
        keys.update(r.params.keys())
    out: dict[str, dict[str, tuple[float, float, int]]] = {}
    for k in sorted(keys):
        buckets: dict[str, list[float]] = defaultdict(list)
        for r in rows:
            if k in r.params:
                buckets[r.params[k]].append(r.score)
        def _stats(s: list[float]) -> tuple[float, float, int]:
            n = len(s)
            avg = sum(s) / n
            std = (sum((x - avg) ** 2 for x in s) / n) ** 0.5
            return avg, std, n
        out[k] = {v: _stats(s) for v, s in buckets.items()}
    return out


_GATE_PASS = 1.0


def _gate_stats(rows: list[_Row]) -> tuple[int, int]:
    """(passed, total) over gate rows; gate passes iff score >= 1.0."""
    gates = [r for r in rows if r.gate]
    return sum(1 for r in gates if r.score >= _GATE_PASS), len(gates)


def _fit_bar_width(max_bar: int, name_max: int, n_cols: int, term_cols: int) -> tuple[int, int]:
    """Return (bar_w, name_w) sized to terminal."""
    for bar_w in range(max_bar, 2, -1):
        cw = _cell_width(bar_w)
        need = 2 + min(name_max, 80) + 2 + n_cols * (cw + 2)
        if need <= term_cols:
            break
    else:
        bar_w = 3
    cw = _cell_width(bar_w)
    name_w = max(20, min(name_max, term_cols - n_cols * (cw + 2) - 4))
    return bar_w, name_w


def pytest_terminal_summary(terminalreporter: "TerminalReporter") -> None:
    config = terminalreporter.config
    rows: list[_Row] = config.stash.get(_RESULTS_KEY, [])
    if not rows:
        return
    max_bar = config.getoption("--scored-bar-width")
    verbose = config.getoption("--scored-verbose")
    tr = terminalreporter
    color = getattr(tr, "hasmarkup", False)
    term_cols = shutil.get_terminal_size((100, 20)).columns
    tr.write_sep("=", "SCORED TESTS")

    # build pivoted view: row_key -> {model -> score}
    cells: dict[str, dict[str, float]] = defaultdict(dict)
    row_order: list[str] = []
    row_func: dict[str, str] = {}
    models_set: set[str] = set()
    for r in rows:
        key = _row_label(r)
        if key not in cells:
            row_order.append(key)
            br = key.find("[")
            row_func[key] = key[:br] if br != -1 else key
        m = r.params.get("model", "")
        cells[key][m] = r.score
        if m:
            models_set.add(m)

    models = sorted(models_set)
    pivoted = len(models) > 0

    if pivoted:
        n = len(models)
        name_max = max(len(k) for k in row_order)
        bar_w, name_w = _fit_bar_width(max_bar, name_max, n, term_cols)
        cw = _cell_width(bar_w)

        # two-line header: backend/ then short model slug
        slugs = [_model_slug(m) for m in models]
        sep = "  "
        header_top = " " * (name_w + 2) + sep.join(f"{b + '/':>{cw}}" for b, _ in slugs)
        header_bot = "test".ljust(name_w) + sep + sep.join(f"{s:>{cw}}" for _, s in slugs)
        tr.write_line(header_top)
        tr.write_line(header_bot)

        # collapse perfect rows
        perfect_rows: list[str] = []
        shown: list[str] = []
        for key in row_order:
            vals = list(cells[key].values())
            if not verbose and vals and all(v >= 0.999 for v in vals):
                perfect_rows.append(key)
            else:
                shown.append(key)

        # sort shown ascending by min cell (worst first)
        shown.sort(key=lambda k: min(cells[k].values()) if cells[k] else 0.0)

        for key in shown:
            cs = cells[key]
            label = key if len(key) <= name_w else key[: name_w - 3] + "..."
            row_cells = sep.join(_fmt_cell(cs.get(m), bar_w, color=color) for m in models)
            tr.write_line(f"{label.ljust(name_w)}{sep}{row_cells}")

        if perfect_rows:
            by_func: dict[str, int] = defaultdict(int)
            for k in perfect_rows:
                by_func[row_func[k]] += 1
            tr.write_sep("-", "perfect (collapsed)")
            total = sum(by_func.values())
            items = [f"{f}({by_func[f]})" for f in sorted(by_func)]
            # wrap to terminal width
            line = "  "
            for it in items:
                add = (", " if line.strip() else "") + it
                if len(line) + len(add) > term_cols - 2 and line.strip():
                    tr.write_line(line)
                    line = "  " + it
                else:
                    line += add
            if line.strip():
                tr.write_line(line)
            tr.write_line(f"  [{total} rows hidden -- --scored-verbose to show]")
    else:
        # single-column fallback (no model param)
        labels = [_row_label(r) for r in rows]
        name_max = max((len(la) for la in labels), default=20)
        bar_w, name_w = _fit_bar_width(max_bar, name_max, 1, term_cols)
        tr.write_line(f"{'test'.ljust(name_w)}  {'score':>5}  bar")
        for label, r in zip(labels, rows):
            la = label if len(label) <= name_w else label[: name_w - 3] + "..."
            tr.write_line(f"{la.ljust(name_w)}  {_fmt_cell(r.score, bar_w, color=color)}")

    quality_rows = [r for r in rows if not r.gate]
    groups = _group_averages(quality_rows)
    threshold = config.getoption("--scored-min")
    failures: list[str] = []
    bar_w_g = min(max_bar, max(3, term_cols // 4))
    for axis, vals in groups.items():
        tr.write_sep("-", f"quality avg by {axis}")
        val_w = max((len(v) for v in vals), default=10)
        for v, (avg, std, n) in sorted(vals.items(), key=lambda kv: kv[1][0]):
            tr.write_line(
                f"  {v.ljust(val_w)}  avg (n={n})  "
                f"{_fmt_score_bar(avg, bar_w_g, color=color, std=std)}"
            )
            if threshold is not None and avg < threshold:
                failures.append(f"{axis}={v} avg {avg:.2f} < {threshold}")

    quality_scores = [r.score for r in quality_rows]
    overall = sum(quality_scores) / len(quality_scores) if quality_scores else 0.0
    overall_std = (sum((x - overall) ** 2 for x in quality_scores) / len(quality_scores)) ** 0.5 if quality_scores else 0.0
    tr.write_sep("-", "overall (quality only)")
    tr.write_line(
        f"  avg (n={len(quality_rows)})  {_fmt_score_bar(overall, bar_w_g, color=color, std=overall_std)}"
    )

    gp, gt = _gate_stats(rows)
    if gt:
        tr.write_sep("-", "compliance gates")
        rate = gp / gt
        tr.write_line(
            f"  passed {gp}/{gt}  {_fmt_score_bar(rate, bar_w_g, color=color)}"
        )

    skip_counts: dict[str, int] = config.stash.get(_SKIP_COUNTS_KEY, {})
    if skip_counts:
        total_skipped = sum(skip_counts.values())
        # normalise: strip "Skipped: " prefix, drop trailing per-run details
        # so e.g. "no result for X/Y/Z -- run `make run`" -> "no result (run `make run`)"
        def _norm_reason(r: str) -> str:
            r = r.removeprefix("Skipped: ").strip()
            if " -- " in r:
                prefix, _, suffix = r.partition(" -- ")
                # drop per-run identifiers in the prefix (everything after first space-separated word-group)
                first_clause = prefix.split(" for ")[0] if " for " in prefix else prefix
                return f"{first_clause} ({suffix})"
            return r
        normalised: dict[str, int] = {}
        for reason, n in skip_counts.items():
            key = _norm_reason(reason)
            normalised[key] = normalised.get(key, 0) + n
        parts = ", ".join(
            f"{n}x {r}" for r, n in sorted(normalised.items(), key=lambda kv: -kv[1])
        )
        tr.write_line(f"  skipped {total_skipped}: {parts}")

    # ---- per-run runtime report ----
    # durations are run-level (same value for every test in a run), so
    # deduplicate by (model, case) before summing or ranking.
    def _fmt_dur(d: float) -> str:
        if d >= 1.0:
            return f"{d:8.3f}s "
        if d >= 1e-3:
            return f"{d * 1e3:8.3f}ms"
        return f"{d * 1e6:8.1f}us"

    tr.write_sep("=", "RUN DURATIONS")
    seen_runs: set[tuple[str, str]] = set()
    by_model: dict[str, float] = defaultdict(float)
    by_model_n: dict[str, int] = defaultdict(int)
    run_cells: list[tuple[str, str, float]] = []  # (model, case, duration)
    for r in rows:
        m = r.params.get("model", "")
        case = r.params.get("case", "")
        run_key = (m, case)
        if run_key in seen_runs:
            continue
        seen_runs.add(run_key)
        by_model[m] += r.duration
        by_model_n[m] += 1
        run_cells.append((m, case or _row_label(r), r.duration))
    if by_model:
        m_w = max(len(m) for m in by_model)
        for m, total in sorted(by_model.items(), key=lambda kv: -kv[1]):
            n = by_model_n[m]
            avg = total / n if n else 0.0
            tr.write_line(f"  {m.ljust(m_w)}  n={n:<3}  total={_fmt_dur(total)}  avg={_fmt_dur(avg)}")
    top_n = 15
    slowest = sorted(run_cells, key=lambda c: -c[2])[:top_n]
    if slowest:
        tr.write_sep("-", f"top {len(slowest)} slowest (model x case)")
        m_w = max(len(c[0]) for c in slowest) or 1
        k_w = min(60, max(len(c[1]) for c in slowest))
        for m, key, d in slowest:
            la = key if len(key) <= k_w else key[: k_w - 3] + "..."
            tr.write_line(f"  {m.ljust(m_w)}  {la.ljust(k_w)}  {_fmt_dur(d)}")

    out_path = config.getoption("--scored-report")
    if out_path:
        _write_json_report(Path(out_path), rows, groups, overall, (gp, gt))

    if failures:
        tr.write_sep("!", "scored threshold failures")
        for f in failures:
            tr.write_line(f"  {f}")


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Set non-zero exit if any group avg falls below --scored-min.

    Runs BEFORE pytest_terminal_summary, so we have to recompute groups
    here rather than relying on a flag set during summary rendering.
    """
    threshold = session.config.getoption("--scored-min", default=None)
    if threshold is None:
        return
    rows: list[_Row] = session.config.stash.get(_RESULTS_KEY, [])
    if not rows:
        return
    # threshold applies to quality rows only; gates are pass/fail elsewhere
    quality_rows = [r for r in rows if not r.gate]
    if not quality_rows:
        return
    overall = sum(r.score for r in quality_rows) / len(quality_rows)
    if overall < threshold:
        if session.exitstatus == 0:
            session.exitstatus = 1
        return
    groups = _group_averages(quality_rows)
    for vals in groups.values():
        for avg, _std, _n in vals.values():
            if avg < threshold:
                if session.exitstatus == 0:
                    session.exitstatus = 1
                return


def _write_json_report(
    path: Path,
    rows: list[_Row],
    groups: dict[str, dict[str, tuple[float, int]]],
    overall: float,
    gates: tuple[int, int],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    gp, gt = gates
    quality_n = sum(1 for r in rows if not r.gate)
    payload = {
        "tests": [
            {
                "id": r.nodeid,
                "score": r.score,
                "scored": r.scored,
                "gate": r.gate,
                "params": r.params,
                "duration_s": r.duration,
            }
            for r in rows
        ],
        "durations": {
            "by_model": {
                m: {
                    "total_s": sum(r.duration for r in rows if r.params.get("model", "") == m),
                    "n": sum(1 for r in rows if r.params.get("model", "") == m),
                }
                for m in sorted({r.params.get("model", "") for r in rows})
            },
        },
        "groups": {
            axis: {v: {"avg": avg, "std": std, "n": n} for v, (avg, std, n) in vals.items()}
            for axis, vals in groups.items()
        },
        "overall": {"avg": overall, "n": quality_n},
        "gates": {"passed": gp, "total": gt, "rate": (gp / gt) if gt else 0.0},
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
