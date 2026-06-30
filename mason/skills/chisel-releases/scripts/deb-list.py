#!/usr/bin/env python3
"""
List files and maintainer scripts inside a debian package to aid chisel slice authoring.

Usage: deb-list.py <package> [arch] [--scripts]
  package    debian package name (e.g. bash, libssl3)
  arch       target architecture (default: host arch; fallback amd64)
             valid values: amd64 arm64 armhf i386 ppc64el riscv64 s390x
  --scripts  print full bodies of all present maintainer scripts

Default output:
  - package header (name, version, arch)
  - Depends: line for wiring essential: entries
  - non-directory files, lexicographically sorted, each prefixed with a type tag:
      [x] executable   [l] symlink -> target   [f] regular file
  - one-line note listing which maintainer scripts are present

Requirements: dpkg-deb, python3, and network access to the ubuntu mirror
(archive.ubuntu.com / ports.ubuntu.com). No sudo, no apt, no populated apt
cache: the .deb is fetched straight from the mirror's Packages index.
Note: the release suite is read from ./chisel.yaml -- run from a chisel-releases
      checkout (or a dir whose chisel.yaml names the suite).
"""

import gzip
import io
import re
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path


# Only install-time scripts matter for slice authoring; remove scripts are irrelevant.
MAINTAINER_SCRIPTS = [
    ("preinst",  "before install"),
    ("postinst", "after install"),
]


def perms_to_octal(perms):
    """Convert symbolic permissions string (e.g. -rwxr-xr-x) to octal (e.g. 0755)."""
    def triplet(t):
        return (4 if t[0] == "r" else 0) + (2 if t[1] == "w" else 0) + (1 if t[2] not in "-T" else 0)
    p = perms[1:10]  # skip type char, take 9 permission chars
    return f"0{triplet(p[0:3])}{triplet(p[3:6])}{triplet(p[6:9])}"


def run(cmd, cwd=None, check=True, capture=False):
    return subprocess.run(cmd, cwd=cwd, check=check, capture_output=capture, text=True)


def host_arch():
    try:
        return run(["dpkg", "--print-architecture"], capture=True).stdout.strip()
    except Exception:
        return "amd64"


# Ubuntu mirrors 403 python-urllib's default UA; apt's UA is always accepted.
_UA = "Debian APT-HTTP/1.3"
_COMPONENTS = ["main", "universe", "restricted", "multiverse"]


def arch_base_url(arch):
    # amd64/i386 live on archive.ubuntu.com; every other port on ports.ubuntu.com.
    if arch in ("amd64", "i386"):
        return "http://archive.ubuntu.com/ubuntu"
    return "http://ports.ubuntu.com/ubuntu-ports"


def read_suite():
    """Base release codename from ./chisel.yaml (archives.ubuntu.suites[0]).

    Minimal parse (no pyyaml): scan for the first token under `suites:` in either
    inline (`suites: [noble, ...]`) or block (`suites:\\n  - noble`) form, then
    strip any pocket suffix so we get the base suite (we add -updates/-security).
    """
    try:
        text = Path("chisel.yaml").read_text()
    except OSError:
        return None
    m = re.search(r"suites:\s*\[\s*([A-Za-z0-9.-]+)", text)         # inline list
    if not m:
        m = re.search(r"suites:\s*\n\s*-\s*([A-Za-z0-9.-]+)", text)  # block list
    if not m:
        return None
    return re.sub(r"-(updates|security|backports|proposed)$", "", m.group(1))


def _fetch(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read()
    except Exception:
        return None


def _filename_from_packages(data, pkg):
    """Find pkg's `Filename:` (pool path) in a gzipped Packages index blob."""
    try:
        text = gzip.GzipFile(fileobj=io.BytesIO(data)).read().decode("utf-8", "replace")
    except Exception:
        return None
    cur = {}
    for line in text.splitlines():
        if not line:
            if cur.get("Package") == pkg:
                return cur.get("Filename")
            cur = {}
        elif ":" in line and not line.startswith(" "):
            k, _, v = line.partition(":")
            cur[k] = v.strip()
    return cur.get("Filename") if cur.get("Package") == pkg else None


def download_deb(pkg, arch, suite, workdir):
    """Fetch pkg's .deb straight from the mirror: walk the Packages indexes for
    suite{,-updates,-security} x components, resolve Filename, download it."""
    base = arch_base_url(arch)
    for try_suite in (f"{suite}-updates", f"{suite}-security", suite):
        for comp in _COMPONENTS:
            data = _fetch(f"{base}/dists/{try_suite}/{comp}/binary-{arch}/Packages.gz")
            if data is None:
                continue
            filename = _filename_from_packages(data, pkg)
            if not filename:
                continue
            deb = _fetch(f"{base}/{filename}")
            if deb is None:
                return None
            dest = Path(workdir) / Path(filename).name
            dest.write_bytes(deb)
            return dest
    return None


def deb_field(deb_path, field):
    result = run(["dpkg-deb", "-f", str(deb_path), field], capture=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else ""


def deb_contents(deb_path):
    """
    Returns list of (path, tag, perms, owner, symlink_target_or_None), lexicographically sorted.
    Directories are excluded -- chisel creates them implicitly.

    dpkg-deb --contents columns: perms links owner/group size date time path [-> target]
    tag: 'x' executable  'l' symlink  'f' regular file
    """
    result = run(["dpkg-deb", "--contents", str(deb_path)], capture=True)
    entries = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if not parts:
            continue
        perms = parts[0]
        owner = parts[1]  # format: user/group
        entry_type = perms[0]  # - d l

        if entry_type == "d":
            continue  # skip directories

        if entry_type == "l" and len(parts) >= 3 and parts[-2] == "->":
            path = parts[-3].lstrip("./")
            symlink_target = parts[-1].lstrip("./")
            tag = "l"
        else:
            path = parts[-1].lstrip("./")
            symlink_target = None
            tag = "x" if "x" in perms[1:] else "f"

        if not path or path == ".":
            continue

        entries.append((f"/{path}", tag, perms_to_octal(perms), owner, symlink_target))

    entries.sort(key=lambda e: e[0])
    return entries


def deb_maintainer_scripts(deb_path, workdir):
    """
    Extracts the control tarball and returns a dict of script_name -> text
    for whichever of preinst/postinst/prerm/postrm are present.
    """
    ctrl_dir = Path(workdir) / "ctrl"
    ctrl_dir.mkdir()
    run(["dpkg-deb", "--control", str(deb_path), str(ctrl_dir)], capture=True)

    scripts = {}
    for name, _ in MAINTAINER_SCRIPTS:
        path = ctrl_dir / name
        if path.exists():
            scripts[name] = path.read_text()
    return scripts


def main():
    args = sys.argv[1:]
    show_scripts = "--scripts" in args
    args = [a for a in args if a != "--scripts"]

    if not args:
        print("usage: deb-list.py <package> [arch] [--scripts]", file=sys.stderr)
        sys.exit(1)

    pkg = args[0]
    arch = args[1] if len(args) > 1 else host_arch()

    suite = read_suite()
    if not suite:
        print("error: could not read the release suite from ./chisel.yaml", file=sys.stderr)
        print("hint:  run deb-list.py from a chisel-releases checkout", file=sys.stderr)
        sys.exit(1)

    with tempfile.TemporaryDirectory() as workdir:
        deb = download_deb(pkg, arch, suite, workdir)
        if not deb:
            print(f"error: {pkg} (arch {arch}) not found on the mirror for suite {suite}", file=sys.stderr)
            print("hint:  check the package name + arch; the mirror must be reachable", file=sys.stderr)
            sys.exit(1)

        version = deb_field(deb, "Version")
        depends  = deb_field(deb, "Depends")

        print(f"package: {pkg}  version: {version}  arch: {arch}\n")

        if depends:
            print(f"Depends: {depends}\n")

        print("files (lexicographic):  [x]=executable  [f]=file  [l]=symlink")
        for path, tag, perms, owner, symlink_target in deb_contents(deb):
            if tag == "l":
                print(f"  [l] {perms} {owner}  {path} -> {symlink_target}")
            else:
                print(f"  [{tag}] {perms} {owner}  {path}")

        scripts = deb_maintainer_scripts(deb, workdir)
        if scripts:
            present = [name for name, _ in MAINTAINER_SCRIPTS if name in scripts]
            print(f"\nmaintainer scripts present: {', '.join(present)}  (re-run with --scripts to view)")

            if show_scripts:
                for name, label in MAINTAINER_SCRIPTS:
                    if name not in scripts:
                        continue
                    print(f"\n--- {name} ({label}) ---")
                    print(scripts[name].rstrip())


if __name__ == "__main__":
    main()
