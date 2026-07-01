#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""check-diff: catch append-only regressions between two versions of an SDF.

Published slices are append-only: removing an SDF, a slice, or a content path
breaks downstream consumers, and the removed-slices CI gate fails on it. Those
are diff-shaped checks -- single-file linting can't see them. This does:

  - an SDF that existed is now gone            -> removed-slices CI fails
  - a slice key that existed is now gone        -> removed-slices CI fails
  - a content path dropped from a kept slice    -> append-only regression

Each is reported unless the package or path genuinely left the archive (which
only the archive can confirm -- a human/CI decides that), so these are warnings
carrying the CI consequence, not hard blocks.

Usage:
  check-diff.py --base <ref> [<pathspec> ...]   # git: compare <ref> vs worktree
  check-diff.py <old.yaml> <new.yaml>           # compare two files directly

--base mode enumerates changed slices/*.yaml via git and compares each against
<ref> (e.g. the release branch a PR targets). Default pathspec: slices/*.yaml.

Output: one finding per line, `SEVERITY  where: message`. Exit code always 0
(advisory); grep for `warn` to gate. Stdlib + pyyaml + git.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


def parse(text: str) -> Any:
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError:
        return None


def slice_paths(doc: Any) -> dict[str, set[str]]:
    """slice name -> set of content paths. empty if not an SDF."""
    out: dict[str, set[str]] = {}
    slices = doc.get("slices") if isinstance(doc, dict) else None
    if not isinstance(slices, dict):
        return out
    for name, body in slices.items():
        contents = body.get("contents") if isinstance(body, dict) else None
        out[name] = set(contents) if isinstance(contents, dict) else set()
    return out


def compare(old_text: str, new_text: str, label: str) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    old, new = slice_paths(parse(old_text)), slice_paths(parse(new_text))
    if not old:
        return rows  # nothing published before, or old wasn't an SDF
    for sname in old:
        if sname not in new:
            rows.append(("warn", f"{label}: {sname}",
                         "slice removed -- removed-slices CI fails unless the package left the archive"))
            continue
        gone = old[sname] - new[sname]
        for path in sorted(gone):
            rows.append(("warn", f"{label}: {sname}",
                         f"path removed from published slice: {path} (append-only regression)"))
    return rows


def git(args: list[str]) -> str | None:
    try:
        r = subprocess.run(["git", *args], capture_output=True, text=True)
    except OSError:
        return None
    return r.stdout if r.returncode == 0 else None


def run_base(base: str, pathspecs: list[str]) -> list[tuple[str, str, str]]:
    specs = pathspecs or ["slices/*.yaml"]
    status = git(["diff", "--name-status", base, "--", *specs])
    if status is None:
        return [("warn", base, "git diff failed -- is this a chisel-releases checkout, and is the ref present?")]
    rows: list[tuple[str, str, str]] = []
    for line in status.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        code, path = parts[0], parts[-1]
        if code.startswith("D"):
            rows.append(("warn", path, "SDF removed -- removed-slices CI fails unless the package left the archive"))
        elif code.startswith(("M", "R")):
            old_text = git(["show", f"{base}:{path}"])
            new = Path(path)
            if old_text is None or not new.exists():
                continue
            rows += compare(old_text, new.read_text(encoding="utf-8"), path)
    return rows


def main(argv: list[str]) -> int:
    if argv and argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    rows: list[tuple[str, str, str]]
    if argv and argv[0] == "--base":
        if len(argv) < 2:
            print("usage: check-diff.py --base <ref> [<pathspec> ...]", file=sys.stderr)
            return 2
        rows = run_base(argv[1], argv[2:])
    elif len(argv) == 2:
        old, new = Path(argv[0]), Path(argv[1])
        rows = compare(old.read_text(encoding="utf-8"), new.read_text(encoding="utf-8"), str(new))
    else:
        print("usage: check-diff.py --base <ref> [<pathspec> ...] | <old.yaml> <new.yaml>", file=sys.stderr)
        return 2

    for sev, where, msg in rows:
        print(f"{sev:5}  {where}: {msg}")
    if not rows:
        print("ok: no append-only regressions")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
