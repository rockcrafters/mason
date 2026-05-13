"""pytest plugin: tests marked @pytest.mark.scored return float in [0,1].

unmarked tests: pass -> 1.0, fail -> 0.0 in summary report.
marked tests must return float in [0,1] or pytest errors.
final terminal summary renders bar chart + per-axis group averages.
"""
from __future__ import annotations

import json
import math
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

def scored(func):
    """Decorator alias -- `@scored` instead of `@pytest.mark.scored`.

    Lazy: defers `pytest.mark.scored` access until the decorator is applied,
    so importing this module from a context where the marker isn't registered
    (e.g. meta tests) doesn't raise PytestUnknownMarkWarning.
    """
    return pytest.mark.scored(func)

_SCORE_KEY = pytest.StashKey[float]()
_PARAMS_KEY = pytest.StashKey[dict[str, str]]()
_BAR_WIDTH_DEFAULT = 10


@dataclass(frozen=True)
class _Row:
    nodeid: str
    score: float
    params: dict[str, str]
    scored: bool


_RESULTS_KEY: pytest.StashKey[list[_Row]] = pytest.StashKey()


def pytest_configure(config: "Config") -> None:
    config.addinivalue_line(
        "markers",
        "scored: test returns float in [0,1] instead of asserting",
    )
    config.stash[_RESULTS_KEY] = []


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
        help="width of ascii score bar (default 10)",
    )
    g.addoption(
        "--scored-min",
        action="store",
        type=float,
        default=None,
        help="fail suite if any group avg falls below this threshold",
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
        outcome = yield
        outcome.get_result()
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
    rows: list[_Row] = item.config.stash[_RESULTS_KEY]
    rows.append(_Row(nodeid=report.nodeid, score=score, params=params, scored=scored))


def _bar(score: float, width: int) -> str:
    filled = int(round(score * width))
    filled = max(0, min(width, filled))
    return "[" + "#" * filled + "-" * (width - filled) + "]"


def _group_averages(rows: list[_Row]) -> dict[str, dict[str, tuple[float, int]]]:
    keys: set[str] = set()
    for r in rows:
        keys.update(r.params.keys())
    out: dict[str, dict[str, tuple[float, int]]] = {}
    for k in sorted(keys):
        buckets: dict[str, list[float]] = defaultdict(list)
        for r in rows:
            if k in r.params:
                buckets[r.params[k]].append(r.score)
        out[k] = {v: (sum(s) / len(s), len(s)) for v, s in buckets.items()}
    return out


def pytest_terminal_summary(terminalreporter: "TerminalReporter") -> None:
    config = terminalreporter.config
    rows: list[_Row] = config.stash.get(_RESULTS_KEY, [])
    if not rows:
        return
    width = config.getoption("--scored-bar-width")
    tr = terminalreporter
    tr.write_sep("=", "SCORED TESTS")
    name_w = max((len(r.nodeid) for r in rows), default=20)
    name_w = min(name_w, 60)
    tr.write_line(f"{'test'.ljust(name_w)}  {'score':>5}  bar")
    for r in rows:
        tr.write_line(
            f"{r.nodeid[:name_w].ljust(name_w)}  {r.score:5.2f}  {_bar(r.score, width)}"
        )

    groups = _group_averages(rows)
    threshold = config.getoption("--scored-min")
    failures: list[str] = []
    for axis, vals in groups.items():
        tr.write_sep("-", f"avg by {axis}")
        val_w = max((len(v) for v in vals), default=10)
        for v, (avg, n) in sorted(vals.items()):
            tr.write_line(
                f"  {v.ljust(val_w)}  avg (n={n})  {avg:5.2f}  {_bar(avg, width)}"
            )
            if threshold is not None and avg < threshold:
                failures.append(f"{axis}={v} avg {avg:.2f} < {threshold}")

    overall = sum(r.score for r in rows) / len(rows)
    tr.write_sep("-", "overall")
    tr.write_line(f"  avg (n={len(rows)})  {overall:5.2f}  {_bar(overall, width)}")

    out_path = config.getoption("--scored-report")
    if out_path:
        _write_json_report(Path(out_path), rows, groups, overall)

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
    # check overall avg + every group axis avg
    overall = sum(r.score for r in rows) / len(rows)
    if overall < threshold:
        if session.exitstatus == 0:
            session.exitstatus = 1
        return
    groups = _group_averages(rows)
    for vals in groups.values():
        for avg, _n in vals.values():
            if avg < threshold:
                if session.exitstatus == 0:
                    session.exitstatus = 1
                return


def _write_json_report(
    path: Path,
    rows: list[_Row],
    groups: dict[str, dict[str, tuple[float, int]]],
    overall: float,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "tests": [
            {
                "id": r.nodeid,
                "score": r.score,
                "scored": r.scored,
                "params": r.params,
            }
            for r in rows
        ],
        "groups": {
            axis: {v: {"avg": avg, "n": n} for v, (avg, n) in vals.items()}
            for axis, vals in groups.items()
        },
        "overall": {"avg": overall, "n": len(rows)},
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
