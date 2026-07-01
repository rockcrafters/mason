#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""regression net for the skill's deterministic checkers.

exercises scripts/check-slice.py, check-test.py, check-diff.py on inline
fixtures and asserts on their findings, so a change that breaks a check fails
loudly. assert-based, no framework. run:  uv run tests/test_checks.py

each checker is invoked as a subprocess via the current interpreter (which, under
uv run, has pyyaml) -- so this tests the real CLI, not imported internals.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "mason/skills/chisel-releases/scripts"


def run(script: str, *args: str) -> str:
    r = subprocess.run(
        [sys.executable, str(SCRIPTS / script), *args],
        capture_output=True, text=True,
    )
    return r.stdout + r.stderr


def write(d: Path, name: str, text: str) -> str:
    p = d / name
    p.write_text(text, encoding="utf-8")
    return str(p)


CLEAN = """\
package: foo
essential:
  - foo_copyright
slices:
  bins:
    essential:
      - libc6_libs
    contents:
      /usr/bin/foo:
  copyright:
    contents:
      /usr/share/doc/foo/copyright:
"""

# unsorted contents + unsorted essential + a man page + hint (invalid on v1).
DIRTY = """\
package: foo
essential:
  - foo_copyright
slices:
  bins:
    essential:
      - libc6_libs
      - base-files_base
    hint: Some tool
    contents:
      /usr/bin/zzz:
      /usr/bin/aaa:
      /usr/share/man/man1/foo.1:
  copyright:
    contents:
      /usr/share/doc/foo/copyright:
"""


def test_check_slice() -> None:
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        out = run("check-slice.py", write(d, "foo.yaml", CLEAN), "--branch", "ubuntu-26.04")
        assert "ok:" in out and "block" not in out, out

        out = run("check-slice.py", write(d, "foo.yaml", DIRTY), "--format", "1")
        assert "contents paths not sorted" in out, out
        assert "essential entries not sorted" in out, out
        assert "hint: is v3+ only" in out, out
        assert "man pages" in out, out

        # filename must match package.
        out = run("check-slice.py", write(d, "bar.yaml", CLEAN), "--format", "3")
        assert "!= filename stem" in out, out

        # v3-essential is a v1/v2 backport, obsolete on v3.
        v3e = "package: foo\nslices:\n  bins:\n    v3-essential:\n      libc6_libs: {arch: [amd64]}\n    contents:\n      /usr/bin/foo:\n  copyright:\n    contents:\n      /usr/share/doc/foo/copyright:\n"
        out = run("check-slice.py", write(d, "foo.yaml", v3e), "--format", "3")
        assert "v3-essential is obsolete on v3" in out, out
        # ...but fine on v1 (no finding).
        out = run("check-slice.py", write(d, "foo.yaml", v3e), "--format", "1")
        assert "v3-essential" not in out, out


def test_check_test() -> None:
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        sdf = write(d, "foo.yaml", CLEAN)
        exercised = write(d, "task.yaml", 'summary: x\nexecute: |\n  rootfs="$(install-slices foo_bins)"\n  chroot "$rootfs" foo --version\n')
        out = run("check-test.py", sdf, exercised)
        assert "ok:" in out, out

        # a test that touches none of the binaries is the red flag (warn).
        missing = write(d, "empty.yaml", "summary: x\nexecute: |\n  true\n")
        out = run("check-test.py", sdf, missing)
        assert "warn" in out and "exercises none" in out, out

        # partial coverage is advisory (info), not a warn: two bins, one tested.
        two = "package: foo\nessential:\n  - foo_copyright\nslices:\n  bins:\n    contents:\n      /usr/bin/foo:\n      /usr/bin/zzz:\n  copyright:\n    contents:\n      /usr/share/doc/foo/copyright:\n"
        sdf2 = write(d, "foo2.yaml", two)
        one = write(d, "one.yaml", 'summary: x\nexecute: |\n  chroot "$r" foo --version\n')
        out = run("check-test.py", sdf2, one)
        assert "info" in out and "1/2 binaries exercised" in out and "zzz" in out, out
        assert "warn" not in out, out


def test_check_diff() -> None:
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        old = write(d, "old.yaml", CLEAN)
        # drop the whole bins slice -> both slice-removed and path-removed shapes.
        shrunk = "package: foo\nessential:\n  - foo_copyright\nslices:\n  copyright:\n    contents:\n      /usr/share/doc/foo/copyright:\n"
        new = write(d, "new.yaml", shrunk)
        out = run("check-diff.py", old, new)
        assert "slice removed" in out, out

        out = run("check-diff.py", old, old)
        assert "ok:" in out, out


def main() -> int:
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"pass  {name}")
    print("all checks pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
