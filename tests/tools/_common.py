"""Shared helpers for tests/tools/ run-dir viewers."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TESTS_DIR = HERE.parent
RUNS_DIR = TESTS_DIR / ".cache" / "runs"


def list_candidates() -> list[Path]:
    if not RUNS_DIR.is_dir():
        return []
    out: list[Path] = []
    for model_dir in sorted(RUNS_DIR.iterdir()):
        if not model_dir.is_dir():
            continue
        for case_dir in sorted(model_dir.iterdir()):
            if case_dir.is_dir() and (case_dir / "metadata.json").exists():
                out.append(case_dir)
    return out


def label(p: Path) -> str:
    return f"{p.parent.name}/{p.name}"


def fzf_pick(labels: list[str]) -> str | None:
    fzf = shutil.which("fzf")
    if not fzf:
        return None
    proc = subprocess.run(
        [fzf, "--prompt=run> ", "--height=40%", "--reverse"],
        input="\n".join(labels),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None
    sel = proc.stdout.strip()
    return sel or None


def _die(msg: str, code: int = 2) -> "None":
    print(msg, file=sys.stderr)
    sys.exit(code)


def resolve(spec: str | None) -> Path:
    cands = list_candidates()
    if not cands:
        _die(f"no runs under {RUNS_DIR}")
    labels = [label(c) for c in cands]
    if spec is None:
        if len(cands) == 1:
            return cands[0]
        pick = fzf_pick(labels)
        if pick is None:
            msg = "multiple runs; pass <spec> or install fzf. candidates:\n  " + "\n  ".join(labels)
            _die(msg)
        spec = pick
    matches = [c for c, lab in zip(cands, labels) if spec in lab]
    if not matches:
        _die(f"no run matches {spec!r}. candidates:\n  " + "\n  ".join(labels))
    if len(matches) > 1:
        _die(
            f"spec {spec!r} ambiguous. matches:\n  "
            + "\n  ".join(label(m) for m in matches)
        )
    return matches[0]
