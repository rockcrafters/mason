"""Orchestrate agent runs: for each (case, model), build sandbox, run agent,
save result + expected + logs into .cache/runs/<model_id>/<case_name>/.

Idempotent: skips pairs that already have a result.yaml unless --force.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path

from framework.agent_runner import get_backend
import logging
import shutil
import sys
import time as _time

import re as _re

# ----- logging: colour for tty, plain for files -----
_COLORS = {
    "DEBUG": "\033[37m",      # grey
    "INFO": "\033[36m",       # cyan
    "WARNING": "\033[33m",    # yellow
    "ERROR": "\033[31m",      # red
    "CRITICAL": "\033[1;31m", # bold red
}
_RESET = "\033[0m"

# per-job colour palette: distinguishable shades of blue / cyan / green,
# all in roughly the same saturation band as the default cyan (xterm-256).
# cycled by index so each job gets a stable colour for its log lines.
_JOB_PALETTE = [
    27, 33, 39, 45, 51,   # blue -> cyan
    50, 49, 48, 47, 46,   # cyan -> green
    44, 38, 75, 79, 80,   # mid blue/teal
    76, 82, 41, 42, 43,   # greens
]
_JOB_COLORS: dict[str, str] = {}
_JOB_RE = _re.compile(r"\[(j\d+)[^\]]*\]")

_T0_OVERALL = _time.monotonic()

_PAIR_LOCK = threading.Lock()
_PAIR_DONE = 0
_PAIR_TOTAL = 0


def _pair_progress() -> str:
    with _PAIR_LOCK:
        return f"{_PAIR_DONE}/{_PAIR_TOTAL}"


def _pair_complete() -> None:
    global _PAIR_DONE
    with _PAIR_LOCK:
        _PAIR_DONE += 1


class _ColorFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
        # warn / error: keep level colour (signal beats per-job hue).
        if record.levelno >= logging.WARNING:
            col = _COLORS.get(record.levelname, "")
            return f"{col}{msg}{_RESET}" if col else msg
        m = _JOB_RE.search(msg)
        if m:
            col = _JOB_COLORS.get(m.group(1), "")
            if col:
                s, e = m.span()
                return f"{msg[:s]}{col}{msg[s:e]}{_RESET}{msg[e:]}"
        col = _COLORS.get(record.levelname, "")
        return f"{col}{msg}{_RESET}" if col else msg


log = logging.getLogger("mason.eval")
log.setLevel(logging.INFO)
log.propagate = False
if not log.handlers:
    _stream = logging.StreamHandler(sys.stdout)
    if sys.stdout.isatty():
        _stream.setFormatter(_ColorFormatter("%(message)s"))
    else:
        _stream.setFormatter(logging.Formatter("%(message)s"))
    log.addHandler(_stream)
from framework.manifest import Case, Manifest, Model, discover_cases, load_manifest
from framework.sandbox import (
    CACHE_DIR,
    REPO_ROOT,
    build_sandbox,
    ensure_chisel_releases_clone,
)


TESTS_DIR = REPO_ROOT / "tests"
MANIFEST_PATH = TESTS_DIR / "manifest.yaml"
CASES_DIR = TESTS_DIR / "cases"
RUNS_DIR = CACHE_DIR / "runs"


def _run_dir(model: Model, case: Case) -> Path:
    return RUNS_DIR / model.id / case.name


def _oneline(s: str) -> str:
    """collapse newlines into visible markers; no truncation."""
    return s.replace("\n", " \\n ")


class _Progress:
    """Log full event detail per claude stream-json event."""

    def __init__(self, tag: str = "") -> None:
        self.t0 = _time.monotonic()
        self.tool_count = 0
        self.msg_count = 0
        self.tag = f"[{tag}] " if tag else ""

    def _stamp(self) -> str:
        now = _time.monotonic()
        return f"[{now - self.t0:5.1f}s | {now - _T0_OVERALL:6.1f}s | {_pair_progress()}]"

    def emit(self, event: dict) -> None:
        etype = event.get("type")
        if etype == "system":
            sub = event.get("subtype")
            if sub == "init":
                model = event.get("model", "?")
                log.info("%s%s init model=%s", self.tag, self._stamp(), model)
            return
        if etype == "assistant":
            message = event.get("message") or {}
            for block in message.get("content") or []:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type")
                if btype == "text":
                    text = block.get("text") or ""
                    if text.strip():
                        self.msg_count += 1
                        log.info("%s%s text: %s", self.tag, self._stamp(), _oneline(text))
                elif btype == "tool_use":
                    self.tool_count += 1
                    name = block.get("name", "?")
                    inp = block.get("input") or {}
                    summary = ", ".join(f"{k}={_oneline(repr(v))}" for k, v in inp.items())
                    log.info(
                        "%s%s tool[%d]: %s(%s)",
                        self.tag, self._stamp(), self.tool_count, name, summary,
                    )
            return
        if etype == "user":
            # detect permission-denied tool_results and surface as warnings
            message = event.get("message") or {}
            for block in message.get("content") or []:
                if not isinstance(block, dict):
                    continue
                if block.get("type") != "tool_result":
                    continue
                if not block.get("is_error"):
                    continue
                content = block.get("content")
                if isinstance(content, str) and "denied" in content.lower():
                    log.warning("%s%s BLOCKED: %s", self.tag, self._stamp(), _oneline(content))
            return
        if etype == "result":
            cost = event.get("total_cost_usd") or event.get("cost_usd")
            usage = event.get("usage") or {}
            it = usage.get("input_tokens")
            ot = usage.get("output_tokens")
            extras = []
            if cost is not None:
                extras.append(f"${cost:.4f}")
            if it is not None:
                extras.append(f"in={it}")
            if ot is not None:
                extras.append(f"out={ot}")
            log.info("%s%s done %s", self.tag, self._stamp(), " ".join(extras))


class _ThreadFilter(logging.Filter):
    """Only accept records emitted from the registered thread -- used to keep
    per-pair run.log files clean when running pairs in parallel."""
    def __init__(self, tid: int) -> None:
        super().__init__()
        self.tid = tid

    def filter(self, record: logging.LogRecord) -> bool:
        return record.thread == self.tid


def _build_prompt(case: Case) -> str:
    # cwd is `/chisel-releases` (bare snapshot, no .git, on the target branch).
    # note: this is an eval of the slice skill itself -- agent has no upstream
    # access; whatever's in cwd is all it gets.
    return (
        f"/mason:write-slice {case.package} {case.branch}\n"
        f"\n"
        f"context: this is an automated eval of the slice skill. cwd is a "
        f"bare snapshot of chisel-releases on `{case.branch}` (no `.git`). "
        f"no upstream fetches available -- work with what's here. write "
        f"`slices/{case.package}.yaml` in place; skip pr / commit steps."
    )


def _skill_hash() -> str:
    h = hashlib.sha256()
    for p in sorted((REPO_ROOT / "skills").rglob("*")):
        if p.is_file():
            h.update(p.read_bytes())
    return h.hexdigest()[:16]


def _filter(name: str, want: str | None) -> bool:
    return want is None or want in name


def _is_valid_cache(out_dir: Path, targets: tuple[str, ...], meta_path: Path) -> bool:
    """Cache hit only if every target file non-empty + parses as yaml + metadata
    reports status=='ok'. Guards against empty / garbage / failed prior runs."""
    import yaml as _yaml
    for pkg in targets:
        p = out_dir / f"{pkg}.yaml"
        if not p.exists() or p.stat().st_size == 0:
            return False
        try:
            if _yaml.safe_load(p.read_text(encoding="utf-8")) is None:
                return False
        except Exception:
            return False
    if not meta_path.exists():
        return False
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    return meta.get("status") == "ok"


def run_pair(
    case: Case,
    model: Model,
    manifest: Manifest,
    chisel_clone: Path,
    *,
    force: bool,
    job_tag: str = "",
) -> dict:
    out_dir = _run_dir(model, case)
    meta_path = out_dir / "metadata.json"
    targets = case.effective_targets

    if not force and _is_valid_cache(out_dir, targets, meta_path):
        return {"case": case.name, "model": model.id, "status": "cached"}

    out_dir.mkdir(parents=True, exist_ok=True)
    prompt = _build_prompt(case)
    skill = _skill_hash()
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]

    with tempfile.TemporaryDirectory(prefix=f"mason-eval-{case.name}-") as tmp:
        sandbox_root = Path(tmp) / "sandbox"
        sandbox = build_sandbox(
            case=case,
            chisel_clone=chisel_clone,
            skills_src=REPO_ROOT / "skills",
            project_md_src=REPO_ROOT / "AGENTS.md",
            workdir=sandbox_root,
        )

        # build minimal plugin tree (.claude-plugin/ + skills/ only) to
        # expose to the agent. avoid binding the whole mason repo (tests,
        # .git, .cache, etc -- agent would see eval framework + manifests).
        plugin_host = Path(tmp) / "mason-plugin"
        plugin_host.mkdir()
        for sub in (".claude-plugin", "skills"):
            src = REPO_ROOT / sub
            if src.exists():
                shutil.copytree(src, plugin_host / sub)
        # neutral in-namespace path
        plugin_agent_path = "/mason-plugin"

        # snapshot ground truth(s) before agent touches anything
        for tgt in sandbox.targets:
            (out_dir / f"{tgt.package}.expected.yaml").write_text(
                tgt.expected_yaml, encoding="utf-8"
            )
        (out_dir / "prompt.txt").write_text(prompt, encoding="utf-8")

        stdout_path = out_dir / "stdout.log"
        stderr_path = out_dir / "stderr.log"
        run_log_path = out_dir / "run.log"
        run_log_handler = logging.FileHandler(run_log_path, mode="w", encoding="utf-8")
        run_log_handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        run_log_handler.addFilter(_ThreadFilter(threading.get_ident()))
        log.addHandler(run_log_handler)
        t0 = time.monotonic()
        tag = f"{job_tag} {case.name}/{model.id}".strip()
        progress = _Progress(tag=tag)
        try:
            backend = get_backend(
                model.backend,
                plugin_mounts=[(plugin_host, plugin_agent_path)],
            )
            result = backend.run(
                model=model.id,
                effort=model.effort,
                prompt=prompt,
                cwd=sandbox.root,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                timeout=manifest.timeout_seconds,
                stuck_timeout=manifest.stuck_timeout_seconds,
                on_event=progress.emit,
            )
            returncode = result.returncode
            err = None
        except Exception as exc:
            returncode = -1
            err = str(exc)
        finally:
            log.removeHandler(run_log_handler)
            run_log_handler.close()
        duration = time.monotonic() - t0

        # snapshot resulting slice(s) -- per target
        present = 0
        for tgt in sandbox.targets:
            if tgt.slice_path.exists():
                (out_dir / f"{tgt.package}.yaml").write_text(
                    tgt.slice_path.read_text(encoding="utf-8"), encoding="utf-8"
                )
                present += 1
        if present == len(sandbox.targets):
            status = "ok"
        elif present == 0:
            status = "missing"
        else:
            status = "partial"

    meta_path.write_text(
        json.dumps(
            {
                "case": {k: (str(v) if isinstance(v, Path) else v) for k, v in asdict(case).items()},
                "model": asdict(model),
                "prompt_hash": prompt_hash,
                "skill_hash": skill,
                "returncode": returncode,
                "duration_s": round(duration, 2),
                "status": status,
                "error": err,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return {"case": case.name, "model": model.id, "status": status, "duration_s": round(duration, 2)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="run mason eval pairs (case x model)")
    ap.add_argument("--force", action="store_true", help="re-run pairs already cached")
    ap.add_argument("--model", default=None, help="only run model ids containing this substring")
    ap.add_argument("--case", default=None, help="only run case names containing this substring")
    ap.add_argument(
        "-j", "--jobs",
        type=int,
        default=4,
        help="parallel pair jobs (default 4; 1 = serial; -1 = unlimited)",
    )
    args = ap.parse_args(argv)
    if args.jobs == 0 or args.jobs < -1:
        ap.error("--jobs must be a positive integer or -1 for unlimited.")

    manifest = load_manifest(MANIFEST_PATH)
    cases = discover_cases(CASES_DIR)
    if not cases:
        print(f"no cases found under {CASES_DIR}", file=sys.stderr)
        return 1
    if not manifest.models:
        print("no models in manifest", file=sys.stderr)
        return 1

    # build the pair list + pre-fetch clones serially (avoid concurrent git
    # ops on the same per-branch dir).
    pairs: list[tuple[Case, Model, Path]] = []
    clones: dict[tuple[str, str | None], Path] = {}
    for case in cases:
        if not _filter(case.name, args.case):
            continue
        key = (case.branch, case.sha)
        clone = clones.get(key)
        if clone is None:
            clone = ensure_chisel_releases_clone(
                url=manifest.chisel_releases_url,
                branch=case.branch,
                sha=case.sha,
            )
            clones[key] = clone
        for model in manifest.models:
            if not _filter(model.id, args.model):
                continue
            pairs.append((case, model, clone))

    global _PAIR_TOTAL
    _PAIR_TOTAL = len(pairs)
    results: list[dict] = []
    n = len(pairs)
    width = max(1, len(str(n)))
    jobs = None if args.jobs == -1 else args.jobs
    job_tags = [f"j{i + 1:0{width}d}" for i in range(n)]
    for i, jt in enumerate(job_tags):
        _JOB_COLORS[jt] = f"\033[38;5;{_JOB_PALETTE[i % len(_JOB_PALETTE)]}m"
    if jobs == 1 or n <= 1:
        for (case, model, clone), jt in zip(pairs, job_tags):
            log.info("-> [%s] %s x %s", jt, case.name, model.id)
            res = run_pair(case, model, manifest, clone, force=args.force, job_tag=jt)
            res["job"] = jt
            results.append(res)
            _pair_complete()
            log.info("[%s] %s", jt, res["status"])
    else:
        log.info("running %d pairs across %s jobs", n, jobs if jobs else "unlimited")
        with ThreadPoolExecutor(max_workers=jobs) as ex:
            futs = {}
            for (case, model, clone), jt in zip(pairs, job_tags):
                fut = ex.submit(
                    run_pair, case, model, manifest, clone,
                    force=args.force, job_tag=jt,
                )
                futs[fut] = (case, model, jt)
            for fut in as_completed(futs):
                case, model, jt = futs[fut]
                try:
                    res = fut.result()
                except Exception as exc:
                    res = {"case": case.name, "model": model.id, "status": f"error: {exc}"}
                res["job"] = jt
                results.append(res)
                _pair_complete()
                log.info("<- [%s] %s x %s  %s", jt, case.name, model.id, res["status"])

    log.info("---")
    for r in results:
        extra = f" ({r.get('duration_s', 0)}s)" if "duration_s" in r else ""
        log.info("[%s] %-20s %-40s %s%s", r.get("job", "--"), r["case"], r["model"], r["status"], extra)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
