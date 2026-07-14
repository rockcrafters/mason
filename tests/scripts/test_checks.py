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


CLEAN_V3 = """\
package: foo
essential:
  foo_copyright:
slices:
  bins:
    essential:
      libc6_libs:
    contents:
      /usr/bin/foo:
  copyright:
    contents:
      /usr/share/doc/foo/copyright:
"""


def test_check_slice() -> None:
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        # list-form essential is the v1/v2 shape; the map form is v3's.
        out = run("check-slice.py", write(d, "foo.yaml", CLEAN), "--format", "1")
        assert "ok:" in out and "block" not in out, out
        out = run("check-slice.py", write(d, "foo.yaml", CLEAN_V3), "--format", "3")
        assert "ok:" in out and "block" not in out, out
        # COVER: shape-vs-format gates both ways -- list on v3 and map on v1 are
        # chisel parse errors the linter must block.
        out = run("check-slice.py", write(d, "foo.yaml", CLEAN), "--format", "3")
        assert "essential must be a map on v3" in out, out
        out = run("check-slice.py", write(d, "foo.yaml", CLEAN_V3), "--format", "1")
        assert "essential-as-map is v3+ only" in out, out

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
            return f'package: foo\nessential:\n  foo_copyright:\nslices:\n  bins:\n    hint: {h}\n    contents:\n      /usr/bin/foo:\n  copyright:\n    contents:\n      /usr/share/doc/foo/copyright:\n'
        out = run("check-slice.py", write(d, "foo.yaml", hint_sdf("System log viewer")), "--format", "3")
        assert "hint" not in out, out  # valid hint, no findings
        out = run("check-slice.py", write(d, "foo.yaml", hint_sdf("The tool that manages absolutely everything here.")), "--format", "3")
        assert "caps it at 40" in out, out            # length is a parse-error block
        assert "start with an article" in out, out    # style warn

        # v3-essential is a v1/v2 backport; a chisel parse error on v3.
        v3e = "package: foo\nslices:\n  bins:\n    v3-essential:\n      libc6_libs: {arch: [amd64]}\n    contents:\n      /usr/bin/foo:\n  copyright:\n    contents:\n      /usr/share/doc/foo/copyright:\n"
        out = run("check-slice.py", write(d, "foo.yaml", v3e), "--format", "3")
        assert "v3-essential is rejected on v3" in out, out
        # ...but fine on v1 (no finding).
        out = run("check-slice.py", write(d, "foo.yaml", v3e), "--format", "1")
        assert "v3-essential" not in out, out


def test_branch_format_from_git() -> None:
    # --branch resolves format from that branch's chisel.yaml in the local git
    # object store (no hardcoded table, no network). Build a throwaway repo whose
    # committed chisel.yaml is v3, then lint a list-form SDF against --branch.
    import os
    env = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"}
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "chisel.yaml").write_text("format: v3\n", encoding="utf-8")
        (d / "foo.yaml").write_text(CLEAN, encoding="utf-8")  # list-form essential

        def git(*a: str) -> None:
            subprocess.run(
                ["git", "-C", str(d), "-c", "user.name=t", "-c", "user.email=t@t",
                 "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", *a],
                check=True, capture_output=True, env=env,
            )

        git("init", "-q", "-b", "ubuntu-99.10")
        git("add", "-A")
        git("commit", "-qm", "base")

        def lint(branch: str) -> str:
            r = subprocess.run(
                [sys.executable, str(SCRIPTS / "check-slice.py"), "foo.yaml", "--branch", branch],
                cwd=str(d), capture_output=True, text=True, env=env,
            )
            return r.stdout + r.stderr

        # v3 resolved from the committed chisel.yaml -> list-form essential blocks.
        assert "essential must be a map on v3" in lint("ubuntu-99.10"), lint("ubuntu-99.10")
        # an unknown ref resolves to no format -> gated checks skipped, no crash.
        out = lint("ubuntu-00.00")
        assert "essential must be a map on v3" not in out, out
        assert "format unknown" in out, out


def test_branch_format_origin_fallback() -> None:
    # the real cross-branch case: the target release is only a remote-tracking
    # ref (no local branch), so format_of_branch must fall back to origin/<branch>.
    import os
    env = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"}

    def git(cwd: Path, *a: str) -> None:
        subprocess.run(
            ["git", "-C", str(cwd), "-c", "user.name=t", "-c", "user.email=t@t",
             "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", *a],
            check=True, capture_output=True, env=env,
        )

    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        origin, clone = d / "origin", d / "clone"
        origin.mkdir()
        # origin default branch 'main' (no chisel.yaml) + ubuntu-88.04 at format v3.
        git(origin, "init", "-q", "-b", "main")
        (origin / "README").write_text("x", encoding="utf-8")
        git(origin, "add", "-A")
        git(origin, "commit", "-qm", "main")
        git(origin, "checkout", "-q", "-b", "ubuntu-88.04")
        (origin / "chisel.yaml").write_text("format: v3\n", encoding="utf-8")
        git(origin, "add", "-A")
        git(origin, "commit", "-qm", "v3 branch")
        git(origin, "checkout", "-q", "main")  # leave HEAD on main so the clone omits ubuntu-88.04
        subprocess.run(["git", "clone", "-q", str(origin), str(clone)],
                       check=True, capture_output=True, env=env)
        (clone / "foo.yaml").write_text(CLEAN, encoding="utf-8")  # list-form essential

        # precondition: no LOCAL ubuntu-88.04 -> only origin/ubuntu-88.04 can resolve it.
        rb = subprocess.run(["git", "-C", str(clone), "rev-parse", "--verify", "-q", "ubuntu-88.04"],
                            capture_output=True, text=True, env=env)
        assert rb.returncode != 0, "expected ubuntu-88.04 to be remote-only"

        r = subprocess.run(
            [sys.executable, str(SCRIPTS / "check-slice.py"), "foo.yaml", "--branch", "ubuntu-88.04"],
            cwd=str(clone), capture_output=True, text=True, env=env,
        )
        out = r.stdout + r.stderr
        # v3 resolved via origin/ubuntu-88.04 -> list-form essential blocks.
        assert "essential must be a map on v3" in out, out


def test_orientation_release_discovery() -> None:
    # hermetic end-to-end for the live-release table: point discovery at a local
    # repo (no network) with a future-eol branch (-> live) and a past-eol branch
    # (-> EOL). asserts the state column is date-derived and the new local-parse
    # end-of-life line prints. exercises the set -e paths under a real invocation.
    import os
    import re as _re
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        origin, clone = d / "origin", d / "clone"
        env = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null",
               "MASON_CHISEL_RELEASES_URL": str(origin)}

        def git(cwd: Path, *a: str) -> None:
            subprocess.run(
                ["git", "-C", str(cwd), "-c", "user.name=t", "-c", "user.email=t@t",
                 "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", *a],
                check=True, capture_output=True, env=env,
            )

        def manifest(fmt: str, ver: str, eol: str) -> str:
            return (f"format: {fmt}\narchives:\n  ubuntu:\n    version: '{ver}'\n"
                    f"    suites: [foo]\nmaintenance:\n  end-of-life: {eol}\n")

        origin.mkdir()
        git(origin, "init", "-q", "-b", "ubuntu-40.04")
        (origin / "chisel.yaml").write_text(manifest("v3", "40.04", "2999-01-01"), encoding="utf-8")
        git(origin, "add", "-A")
        git(origin, "commit", "-qm", "live lts")
        git(origin, "checkout", "-q", "-b", "ubuntu-30.10")
        (origin / "chisel.yaml").write_text(manifest("v2", "30.10", "2000-01-01"), encoding="utf-8")
        git(origin, "add", "-A")
        git(origin, "commit", "-qm", "dead interim")
        git(origin, "checkout", "-q", "ubuntu-40.04")  # HEAD -> the future-eol branch
        subprocess.run(["git", "clone", "-q", str(origin), str(clone)],
                       check=True, capture_output=True, env=env)

        r = subprocess.run(["bash", str(SCRIPTS / "orientation")],
                           cwd=str(clone), capture_output=True, text=True, env=env)
        out = r.stdout + r.stderr
        assert r.returncode == 0, out
        # local parse of the checked-out branch: the new end-of-life line.
        assert _re.search(r"end-of-life:\s+2999-01-01", out), out
        # discovery table: state is eol-vs-today, formats normalised, not branch presence.
        assert "live releases:" in out, out
        assert _re.search(r"ubuntu-40\.04\s+v3\s+2999-01-01\s+live", out), out
        assert _re.search(r"ubuntu-30\.10\s+v2\s+2000-01-01\s+EOL", out), out


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
    # the draft is conformant by construction: check-slice passes on it, on the
    # format it was drafted for (essential shape is format-gated).
    with tempfile.TemporaryDirectory() as td:
        p = write(Path(td), "foo.yaml", sdf)
        out = run("check-slice.py", p, "--format", "1")
        assert "ok:" in out, out
    sdf3 = m.build_sdf("foo", "libc6", entries, fmt=3)
    assert "  foo_copyright:" in sdf3 and "- foo_copyright" not in sdf3, sdf3
    with tempfile.TemporaryDirectory() as td:
        p = write(Path(td), "foo.yaml", sdf3)
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
