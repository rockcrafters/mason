#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""check-test: how well does the spread test exercise a slice's binaries?

"Please test every binary being delivered" is a recurring reviewer ask, but it
isn't a hard rule -- alternatives symlinks, multi-call binaries, and big utility
suites are legitimately tested representatively. So this reports coverage rather
than demanding every binary: it lists the executables an SDF declares (explicit
paths under /usr/bin, /usr/sbin, /bin, /sbin, /usr/libexec) and how many the
package's spread test references.

It cannot judge whether a test is *meaningful* -- only that binaries are
referenced. Functional depth and hygiene (hermetic, bounded waits, one rootfs
per test) are still on the author -- see the write-slice / review-slice docs.

Usage:
  check-test.py <slices/pkg.yaml> [<task.yaml>]

With no task.yaml, it looks for tests/spread/integration/<pkg>/task.yaml under
the cwd, and folds in any sibling *.sh helper files.

Output: one finding per line, `SEVERITY  where: message`.
  warn   no spread test at all, or a test that exercises none of the binaries.
  info   partial coverage (lists the untested binaries to review), or nothing
         to check (the SDF declares no explicit binaries).
Exit code is always 0 (advisory); grep for `warn` to gate. Stdlib + pyyaml.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import yaml

BIN_DIRS = ("/usr/bin/", "/usr/sbin/", "/bin/", "/sbin/", "/usr/libexec/")


def declared_binaries(doc: Any) -> dict[str, str]:
    """basename -> slice name, for each explicit executable path (skips globs/dirs)."""
    out: dict[str, str] = {}
    slices = doc.get("slices") if isinstance(doc, dict) else None
    if not isinstance(slices, dict):
        return out
    for sname, body in slices.items():
        contents = body.get("contents") if isinstance(body, dict) else None
        if not isinstance(contents, dict):
            continue
        for path in contents:
            if not isinstance(path, str) or not any(path.startswith(d) for d in BIN_DIRS):
                continue
            if path.endswith("/") or "*" in path or "?" in path:
                continue
            out.setdefault(path.rsplit("/", 1)[-1], sname)
    return out


def test_text(sdf: Path, task_arg: str | None) -> tuple[str, Path | None]:
    """concatenated text of the package's test files, and the task.yaml path."""
    if task_arg:
        task = Path(task_arg)
    else:
        pkg = sdf.name[:-5] if sdf.name.endswith(".yaml") else sdf.stem
        task = Path("tests/spread/integration") / pkg / "task.yaml"
    if not task.exists():
        return "", None
    parts = [task.read_text(encoding="utf-8")]
    for sh in sorted(task.parent.glob("*.sh")):
        parts.append(sh.read_text(encoding="utf-8"))
    return "\n".join(parts), task


def check(sdf: Path, task_arg: str | None) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    try:
        doc = yaml.safe_load(sdf.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        rows.append(("warn", str(sdf), f"cannot read SDF: {e}"))
        return rows

    bins = declared_binaries(doc)
    text, task = test_text(sdf, task_arg)
    if not bins:
        rows.append(("info", str(sdf), "no explicit binaries to exercise"))
        return rows
    if task is None:
        rows.append(("warn", str(sdf), "no spread test found -- add one that exercises the binaries"))
        return rows

    exercised = {n for n in bins if re.search(rf"\b{re.escape(n)}\b", text)}
    untested = sorted(set(bins) - exercised)
    if not exercised:
        # the real red flag: a test exists but touches none of the binaries.
        rows.append(("warn", str(task), f"spread test exercises none of the {len(bins)} declared binaries"))
    elif untested:
        # partial coverage is normal for big suites and alternatives symlinks;
        # surface the gap as info so the author can judge, don't alarm.
        shown = ", ".join(untested[:12]) + (f", +{len(untested) - 12} more" if len(untested) > 12 else "")
        rows.append(("info", str(task), f"{len(exercised)}/{len(bins)} binaries exercised; untested: {shown}"))
    return rows


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("-")]
    if argv and argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if not args:
        print("usage: check-test.py <slices/pkg.yaml> [<task.yaml>]", file=sys.stderr)
        return 2
    sdf = Path(args[0])
    task_arg = args[1] if len(args) > 1 else None
    rows = check(sdf, task_arg)
    for sev, where, msg in rows:
        print(f"{sev:5}  {where}: {msg}")
    if not rows:
        print(f"ok: {sdf} binaries all exercised")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
