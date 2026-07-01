#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""review-diff: run every deterministic check over a chisel-releases PR diff.

one command for a PR-review bot. given the branch a PR targets, it finds the
changed SDFs and runs the three checkers over them:

  - check-slice   static conventions (sorting, naming, copyright, clutter, ...)
  - check-test    binary test coverage
  - check-diff    append-only regressions (removed SDF / slice / path)

then prints one report grouped by severity, with a verdict, and exits non-zero
if anything `block`s -- so a CI job or bot can gate on it without an agent.

Usage:
  review-diff.py --base <ref>

Run from the chisel-releases checkout root (the checkers read chisel.yaml for
the format version). pyyaml is declared so the checkers, invoked via this same
interpreter, can import it.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SEVERITIES = ("block", "warn", "info")


def git(args: list[str]) -> str | None:
    try:
        r = subprocess.run(["git", *args], capture_output=True, text=True)
    except OSError:
        return None
    return r.stdout if r.returncode == 0 else None


def run_check(script: str, *args: str) -> list[str]:
    r = subprocess.run([sys.executable, str(HERE / script), *args], capture_output=True, text=True)
    lines = (r.stdout + r.stderr).splitlines()
    return [ln for ln in lines if ln.split() and ln.split()[0] in SEVERITIES]


def changed_slices(base: str) -> list[str] | None:
    status = git(["diff", "--name-status", base, "--", "slices/*.yaml"])
    if status is None:
        return None
    out = []
    for line in status.splitlines():
        parts = line.split("\t")
        # added or modified (skip deletions -- check-diff reports those).
        if len(parts) >= 2 and parts[0][:1] in ("A", "M", "R") and Path(parts[-1]).exists():
            out.append(parts[-1])
    return out


def main(argv: list[str]) -> int:
    if argv and argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if len(argv) < 2 or argv[0] != "--base":
        print("usage: review-diff.py --base <ref>", file=sys.stderr)
        return 2
    base = argv[1]

    changed = changed_slices(base)
    if changed is None:
        print(f"error: git diff against '{base}' failed -- is this a checkout, and is the ref present?", file=sys.stderr)
        return 2

    findings: list[str] = []
    if changed:
        findings += run_check("check-slice.py", *changed)
        for sdf in changed:
            findings += run_check("check-test.py", sdf)
    findings += run_check("check-diff.py", "--base", base)

    rank = {s: i for i, s in enumerate(SEVERITIES)}
    findings.sort(key=lambda ln: rank.get(ln.split()[0], 9))
    blocks = sum(ln.startswith("block") for ln in findings)
    warns = sum(ln.startswith("warn") for ln in findings)

    print(f"reviewed {len(changed)} changed SDF(s) against {base}: {blocks} block, {warns} warn, {len(findings) - blocks - warns} info")
    for ln in findings:
        print(ln)
    verdict = "request-changes" if blocks else ("comment" if warns else "approve")
    print(f"verdict: {verdict}")
    return 1 if blocks else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
