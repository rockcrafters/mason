"""View diff between expected and actual slice yaml for a cached run."""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from tools._common import _die, resolve


def _find_pair(run_dir: Path) -> tuple[Path, Path]:
    expected = list(run_dir.glob("*.expected.yaml"))
    if not expected:
        _die(f"no *.expected.yaml in {run_dir}")
    if len(expected) > 1:
        _die(f"multiple *.expected.yaml in {run_dir}")
    exp = expected[0]
    actual = run_dir / exp.name.removesuffix(".expected.yaml").__add__(".yaml")
    if not actual.exists():
        _die(f"actual {actual} missing")
    return exp, actual


def _pick_tool(requested: str, tty: bool) -> list[str]:
    """Return command prefix; appended w/ <expected> <actual>."""
    if requested == "none" or not tty:
        return ["diff", "-u"]
    if requested == "auto":
        if shutil.which("delta"):
            return ["delta"]
        if shutil.which("git"):
            return ["git", "diff", "--no-index", "--color=always"]
        if shutil.which("diff"):
            return ["diff", "-u", "--color=always"]
        return ["diff", "-u"]
    if requested == "delta":
        if not shutil.which("delta"):
            _die("delta not installed")
        return ["delta"]
    if requested == "git":
        if not shutil.which("git"):
            _die("git not installed")
        return ["git", "diff", "--no-index", "--color=always"]
    if requested == "diff":
        return ["diff", "-u", "--color=always" if tty else "-u"]
    _die(f"unknown --tool {requested}")
    return []  # unreachable


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="diff expected vs actual for a cached run")
    ap.add_argument("spec", nargs="?", default=None, help="substring of <model>/<case>")
    ap.add_argument(
        "--tool",
        default="auto",
        choices=["auto", "diff", "git", "delta", "none"],
        help="diff backend (default: auto -- delta > git > diff)",
    )
    args = ap.parse_args(argv)

    run_dir = resolve(args.spec)
    expected, actual = _find_pair(run_dir)
    tty = sys.stdout.isatty()
    cmd = _pick_tool(args.tool, tty) + [str(expected), str(actual)]
    proc = subprocess.run(cmd)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
