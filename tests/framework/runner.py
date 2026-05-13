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
import time
from dataclasses import asdict
from pathlib import Path

from framework.agent_runner import get_backend
import logging
import shutil
import sys
import time as _time

# ----- logging: colour for tty, plain for files -----
_COLORS = {
    "DEBUG": "\033[37m",      # grey
    "INFO": "\033[36m",       # cyan
    "WARNING": "\033[33m",    # yellow
    "ERROR": "\033[31m",      # red
    "CRITICAL": "\033[1;31m", # bold red
}
_RESET = "\033[0m"


class _ColorFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
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

    def __init__(self) -> None:
        self.t0 = _time.monotonic()
        self.tool_count = 0
        self.msg_count = 0

    def _stamp(self) -> str:
        return f"[{_time.monotonic() - self.t0:5.1f}s]"

    def emit(self, event: dict) -> None:
        etype = event.get("type")
        if etype == "system":
            sub = event.get("subtype")
            if sub == "init":
                model = event.get("model", "?")
                log.info("   %s init model=%s", self._stamp(), model)
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
                        log.info("   %s text: %s", self._stamp(), _oneline(text))
                elif btype == "tool_use":
                    self.tool_count += 1
                    name = block.get("name", "?")
                    inp = block.get("input") or {}
                    summary = ", ".join(f"{k}={_oneline(repr(v))}" for k, v in inp.items())
                    log.info(
                        "   %s tool[%d]: %s(%s)",
                        self._stamp(), self.tool_count, name, summary,
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
                    log.warning("   %s BLOCKED: %s", self._stamp(), _oneline(content))
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
            log.info("   %s done %s", self._stamp(), " ".join(extras))


def _build_prompt(case: Case) -> str:
    # cwd is `/chisel-releases` (bare snapshot, no .git, on the target branch).
    # note: this is an eval of the slice skill itself -- agent has no upstream
    # access; whatever's in cwd is all it gets.
    return (
        f"/slice {case.package} {case.branch}\n"
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


def _is_valid_cache(result_path: Path, meta_path: Path) -> bool:
    """Cache hit only if result file non-empty + parses as yaml + metadata
    reports status=='ok'. Guards against empty / garbage / failed prior runs
    being treated as cached."""
    if not result_path.exists() or result_path.stat().st_size == 0:
        return False
    try:
        import yaml as _yaml
        if _yaml.safe_load(result_path.read_text(encoding="utf-8")) is None:
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
) -> dict:
    out_dir = _run_dir(model, case)
    result_path = out_dir / f"{case.package}.yaml"
    expected_path = out_dir / f"{case.package}.expected.yaml"
    meta_path = out_dir / "metadata.json"

    if not force and _is_valid_cache(result_path, meta_path):
        return {"case": case.name, "model": model.id, "status": "cached"}

    out_dir.mkdir(parents=True, exist_ok=True)
    prompt = _build_prompt(case)
    skill = _skill_hash()
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]

    with tempfile.TemporaryDirectory(prefix=f"mason-eval-{case.name}-") as tmp:
        sandbox_root = Path(tmp) / "sandbox"
        sandbox = build_sandbox(
            package=case.package,
            branch=case.branch,
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

        # snapshot ground truth before agent touches anything
        expected_path.write_text(sandbox.expected_yaml, encoding="utf-8")
        (out_dir / "prompt.txt").write_text(prompt, encoding="utf-8")

        stdout_path = out_dir / "stdout.log"
        stderr_path = out_dir / "stderr.log"
        run_log_path = out_dir / "run.log"
        run_log_handler = logging.FileHandler(run_log_path, mode="w", encoding="utf-8")
        run_log_handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        log.addHandler(run_log_handler)
        t0 = time.monotonic()
        progress = _Progress()
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

        # snapshot resulting slice
        if sandbox.slice_path.exists():
            result_path.write_text(
                sandbox.slice_path.read_text(encoding="utf-8"), encoding="utf-8"
            )
            status = "ok"
        else:
            # agent failed to produce file
            status = "missing"

    meta_path.write_text(
        json.dumps(
            {
                "case": asdict(case),
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
    args = ap.parse_args(argv)

    manifest = load_manifest(MANIFEST_PATH)
    cases = discover_cases(CASES_DIR)
    if not cases:
        print(f"no cases found under {CASES_DIR}", file=sys.stderr)
        return 1
    if not manifest.models:
        print("no models in manifest", file=sys.stderr)
        return 1

    clone = ensure_chisel_releases_clone(
        url=manifest.chisel_releases_url,
        branch=manifest.chisel_releases_default_branch,
        sha=manifest.chisel_releases_sha,
    )

    results: list[dict] = []
    for case in cases:
        if not _filter(case.name, args.case):
            continue
        for model in manifest.models:
            if not _filter(model.id, args.model):
                continue
            log.info("-> %s x %s", case.name, model.id)
            res = run_pair(case, model, manifest, clone, force=args.force)
            results.append(res)
            log.info("   %s", res["status"])

    log.info("---")
    for r in results:
        extra = f" ({r.get('duration_s', 0)}s)" if "duration_s" in r else ""
        log.info("  %-20s %-40s %s%s", r["case"], r["model"], r["status"], extra)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
