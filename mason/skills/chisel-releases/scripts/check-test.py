#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""check-test: does the spread test exercise every binary a slice ships?

"Please test every binary being delivered" is a top reviewer rejection. This
checks it deterministically: it lists the executables an SDF declares (explicit
paths under /usr/bin, /usr/sbin, /bin, /sbin, /usr/libexec) and reports any whose
name never appears in the package's spread test.

It cannot judge whether a test is *meaningful* -- only that each binary is
referenced somewhere. Depth of functional testing, and hygiene (hermetic,
bounded waits, one rootfs per test), are still on the author -- see the
write-slice / review-slice command docs.

Usage:
  check-test.py <slices/pkg.yaml> [<task.yaml>]

With no task.yaml, it looks for tests/spread/integration/<pkg>/task.yaml under
the cwd, and folds in any sibling *.sh helper files.

Output: one finding per line, `SEVERITY  where: message`.
  warn   a binary is untested, or no test file exists -- reviewers push back.
  info   nothing to check (the SDF declares no explicit binaries).
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


def check(sdf: Path, task_arg: str | None) -> tuple[list[tuple[str, str, str]], bool]:
    rows: list[tuple[str, str, str]] = []
    try:
        doc = yaml.safe_load(sdf.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        rows.append(("warn", str(sdf), f"cannot read SDF: {e}"))
        return rows, False

    bins = declared_binaries(doc)
    text, task = test_text(sdf, task_arg)
    if not bins:
        rows.append(("info", str(sdf), "no explicit binaries to exercise"))
        return rows, False
    if task is None:
        rows.append(("warn", str(sdf), "no spread test found -- every binary needs one exercised"))
        return rows, True

    for name, sname in sorted(bins.items()):
        if not re.search(rf"\b{re.escape(name)}\b", text):
            rows.append(("warn", f"{task}", f"binary '{name}' ({doc.get('package')}_{sname}) is never exercised"))
    return rows, True


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
    rows, _ = check(sdf, task_arg)
    warns = 0
    for sev, where, msg in rows:
        warns += sev == "warn"
        print(f"{sev:5}  {where}: {msg}")
    if not rows:
        print(f"ok: every binary in {sdf} is exercised")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
