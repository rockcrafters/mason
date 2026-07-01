"""pytest regression net for the skill's deterministic checkers.

Exercises the scripts under mason/skills/chisel-releases/scripts/ on inline
fixtures via subprocess, so this tests the real CLI, not imported internals. The
subprocessed scripts need pyyaml, which must be present under the runner's
interpreter. Run:

    uv run --with pyyaml --with pytest pytest tests/scripts/
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "mason/skills/chisel-releases/scripts"


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

        # hint validation (v3): a good hint is clean; length/style are checked.
        def hint_sdf(h):
            return f'package: foo\nessential:\n  - foo_copyright\nslices:\n  bins:\n    hint: {h}\n    contents:\n      /usr/bin/foo:\n  copyright:\n    contents:\n      /usr/share/doc/foo/copyright:\n'
        out = run("check-slice.py", write(d, "foo.yaml", hint_sdf("System log viewer")), "--format", "3")
        assert "hint" not in out, out  # valid hint, no findings
        out = run("check-slice.py", write(d, "foo.yaml", hint_sdf("The tool that manages absolutely everything here.")), "--format", "3")
        assert "caps it at 40" in out, out            # length is a parse-error block
        assert "start with an article" in out, out    # style warn

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


def test_scaffold_test() -> None:
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        sdf = write(d, "foo.yaml", CLEAN)  # ships /usr/bin/foo in the bins slice.
        out = run("scaffold-test.py", str(sdf))
        assert "install-slices foo_bins" in out and 'chroot "$rootfs" foo' in out, out
        # round-trip: the scaffold exercises every binary by construction, so
        # check-test reports full coverage on it.
        task = write(d, "task.yaml", out)
        ct = run("check-test.py", str(sdf), str(task))
        assert "ok:" in ct, ct


def test_robustness() -> None:
    # a PR-review bot runs on arbitrary diffs; the checkers must degrade
    # gracefully on malformed SDFs, never crash. each of these should produce a
    # block (or clean handling), never a Python traceback.
    cases = {
        "empty.yaml": "",
        "scalar.yaml": "just a string",
        "list.yaml": "- a\n- b\n",
        "wrongtypes.yaml": "package: [1, 2]\nslices: not-a-map\n",
        "numkey.yaml": "package: x\nslices:\n  bins:\n    contents:\n      123: {}\n",
        "badyaml.yaml": 'key: "unclosed\n',
    }
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        for name, text in cases.items():
            for tool in ("check-slice.py", "check-test.py", "scaffold-test.py"):
                out = run(tool, write(d, name, text))
                assert "Traceback" not in out, f"{tool} crashed on {name}: {out}"


def test_draft_sdf() -> None:
    import importlib.util
    # don't write __pycache__ into the installed skill's scripts dir.
    prev, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec = importlib.util.spec_from_file_location("deblist", str(SCRIPTS / "deb-list.py"))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
    finally:
        sys.dont_write_bytecode = prev
    entries = [
        ("/usr/bin/foo", "x", "0755", "root/root", None),
        ("/usr/lib/x86_64-linux-gnu/libfoo.so.1", "f", "0644", "root/root", None),
        ("/usr/include/foo.h", "f", "0644", "root/root", None),          # headers
        ("/var/lib/foo/state", "f", "0644", "root/root", None),          # var
        ("/usr/share/man/man1/foo.1", "f", "0644", "root/root", None),   # clutter
        ("/usr/share/doc/foo/copyright", "f", "0644", "root/root", None),
    ]
    sdf = m.build_sdf("foo", "libc6", entries)
    assert "/usr/lib/*-linux-*/libfoo.so.1:" in sdf, sdf  # multiarch triple globbed
    assert "/usr/share/man" not in sdf, sdf               # clutter dropped
    assert "headers:" in sdf and "/usr/include/foo.h:" in sdf, sdf
    assert "var:" in sdf and "/var/lib/foo/state:" in sdf, sdf
    # the draft is conformant by construction: check-slice passes on it.
    with tempfile.TemporaryDirectory() as td:
        p = write(Path(td), "foo.yaml", sdf)
        out = run("check-slice.py", p, "--format", "3")
        assert "ok:" in out, out

    # shared-copyright package: ships /usr/share/doc/<pkg> as a symlink, no
    # copyright file. the doc dir must go in copyright, not be dropped, and no
    # bogus /usr/share/doc/<pkg>/copyright path should be invented.
    shared = m.build_sdf("libgcc-s1", "gcc-base", [
        ("/usr/lib/x86_64-linux-gnu/libgcc_s.so.1", "f", "0644", "root/root", None),
        ("/usr/share/doc/libgcc-s1", "l", "0777", "root/root", "gcc-base"),
    ])
    assert "/usr/share/doc/libgcc-s1:" in shared, shared
    assert "/usr/share/doc/libgcc-s1/copyright" not in shared, shared
