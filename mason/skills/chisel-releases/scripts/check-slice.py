#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""check-slice: deterministic static linter for chisel slice definition files.

Checks the mechanical conventions reviewers and CI enforce -- the rules that do
NOT need judgement or a rootfs cut. Use it two ways:

  - authoring: self-check an SDF before commit (write-slice step 8).
  - review:    the deterministic first pass of a review (review-slice), so the
               agent only spends judgement on deps, tests, and design.

It does NOT replace `chisel cut` (installability) or spread tests
(functionality). It only checks the SDF text.

Usage:
  check-slice.py <slice.yaml> [<slice2.yaml> ...] [--format N | --branch NAME]

Format detection (needed for version-gated fields hint/prefer/v3-essential and
essential-as-map): --format wins, else --branch maps to a format, else the
format: field of ./chisel.yaml, else unknown (gated checks are skipped, noted).

Output: one finding per line, `SEVERITY  file: where: message`.
  block  hard gate -- chisel won't parse it, or CI/lint fails. exit code 1.
  warn   reviewers reliably reject this. exit code stays 0.
  info   nit, or a check skipped because format is unknown.

Exit code is 1 if any block finding, else 0. Stdlib + pyyaml only; runs under
`uv run` (per the shebang) or `python3 check-slice.py` if pyyaml is importable.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import yaml

# known-bad slice names reviewers reject, mapped to the right one. by-function
# and per-binary names (e.g. printing-text, ls-bin, journal) are legitimate, so
# only these exact mistakes are flagged -- not "anything off a fixed vocabulary".
BAD_SLICE_NAMES = {"bin": "bins", "lib": "libs", "all": "core"}

# Debian arch names -- always lowercase, never x86_64/aarch64. (arch-list order
# is not enforced: real SDFs use a priority order, not alphabetical.)
VALID_ARCHES = {"amd64", "arm64", "armhf", "i386", "ppc64el", "riscv64", "s390x"}

# branch -> chisel.yaml format version (mirrors tests/scorers/_lib.py).
BRANCH_FORMAT = {
    "ubuntu-20.04": 1, "ubuntu-22.04": 1, "ubuntu-24.04": 1,
    "ubuntu-25.10": 2, "ubuntu-26.04": 3,
}

SNAME_RE = re.compile(r"^[a-z][a-z0-9-]{2,}$")

# paths a minimal rootfs never needs -- see shared/CHISEL.md "Exclude by Default".
CLUTTER = {
    "man pages": ("/usr/share/man/", "/usr/man/"),
    "shell completions": (
        "/usr/share/bash-completion/", "/usr/share/fish/",
        "/usr/share/zsh/", "/etc/bash_completion.d/",
    ),
    "doc-base/lintian metadata": ("/usr/share/doc-base/", "/usr/share/lintian/"),
}


class Findings:
    def __init__(self, file: str) -> None:
        self.file = file
        self.rows: list[tuple[str, str, str]] = []

    def add(self, sev: str, where: str, msg: str) -> None:
        self.rows.append((sev, where, msg))

    def block(self, where: str, msg: str) -> None:
        self.add("block", where, msg)

    def warn(self, where: str, msg: str) -> None:
        self.add("warn", where, msg)

    def info(self, where: str, msg: str) -> None:
        self.add("info", where, msg)


def slices_of(doc: Any) -> dict:
    s = doc.get("slices") if isinstance(doc, dict) else None
    return s if isinstance(s, dict) else {}


def is_sorted(keys: list) -> bool:
    strs = [k for k in keys if isinstance(k, str)]
    return strs == sorted(strs)


def check_filename(doc: Any, path: Path, f: Findings) -> None:
    stem = path.name[:-5] if path.name.endswith(".yaml") else path.stem
    pkg = doc.get("package") if isinstance(doc, dict) else None
    if not isinstance(pkg, str) or not pkg:
        f.block("package:", "missing top-level package: field")
    elif pkg != stem:
        f.block("package:", f"package: '{pkg}' != filename stem '{stem}'")


def check_essential_sorted(doc: Any, f: Findings) -> None:
    # per-slice essential + contents sorting is the CI lint gate (LC_COLLATE=C,
    # sort -C). the top-level essential is not CI-gated, but keep it sorted for
    # consistency -- so warn, don't block.
    if isinstance(doc.get("essential"), list):
        if not is_sorted(doc["essential"]):
            f.warn("essential:", "global essential entries not sorted")
    for name, body in slices_of(doc).items():
        ess = body.get("essential") if isinstance(body, dict) else None
        if isinstance(ess, list) and not is_sorted(ess):
            f.block(f"{name}.essential", "essential entries not sorted")
        elif isinstance(ess, dict) and not is_sorted(list(ess.keys())):
            f.block(f"{name}.essential", "essential map keys not sorted")


def check_slices(doc: Any, fmt: int | None, f: Findings) -> None:
    slices = slices_of(doc)
    if not slices:
        f.block("slices:", "no slices: map -- not a slice definition file")
        return
    pkg = doc.get("package") if isinstance(doc.get("package"), str) else ""

    # copyright is mandatory.
    cp = slices.get("copyright")
    if not isinstance(cp, dict):
        f.block("slices:", "no copyright slice (every SDF must ship one)")
    else:
        contents = cp.get("contents") if isinstance(cp.get("contents"), dict) else {}
        if pkg and f"/usr/share/doc/{pkg}/copyright" not in contents:
            f.block("copyright", f"missing /usr/share/doc/{pkg}/copyright")
    ess = doc.get("essential")
    if pkg and not (isinstance(ess, list) and f"{pkg}_copyright" in ess) \
            and not (isinstance(ess, dict) and f"{pkg}_copyright" in ess):
        f.warn("essential:", f"{pkg}_copyright not in global essential (so not every slice ships it)")

    for name, body in slices.items():
        if not isinstance(name, str) or not SNAME_RE.match(name):
            f.block(f"slices.{name}", "slice name must match ^[a-z][a-z0-9-]{2,}$")
        if not isinstance(body, dict):
            continue
        check_slice_body(name, body, fmt, f)


def check_slice_body(name: str, body: dict, fmt: int | None, f: Findings) -> None:
    if name in BAD_SLICE_NAMES:
        f.warn(f"slices.{name}", f"use '{BAD_SLICE_NAMES[name]}' not '{name}'")

    if "hint" in body and (fmt is not None and fmt < 3):
        f.block(f"{name}.hint", f"hint: is v3+ only (format is v{fmt})")

    contents = body.get("contents")
    if not isinstance(contents, dict):
        return
    keys = list(contents.keys())
    if not is_sorted(keys):
        f.block(f"{name}.contents", "contents paths not sorted (bytewise/ASCII)")
    for path, entry in contents.items():
        check_path(name, path, entry, fmt, f)


def check_path(sname: str, path: Any, entry: Any, fmt: int | None, f: Findings) -> None:
    if not isinstance(path, str) or not path.startswith("/"):
        f.block(f"{sname}: {path}", "path must be absolute (start with /)")
        return
    for label, prefixes in CLUTTER.items():
        if any(path.startswith(p) for p in prefixes):
            f.warn(f"{sname}: {path}", f"{label} not shipped in minimal rootfs")
    if path.startswith("/usr/share/doc/") and not path.endswith("/copyright"):
        f.warn(f"{sname}: {path}", "doc clutter: only the copyright file is shipped")

    if not isinstance(entry, dict):
        return
    if "prefer" in entry and (fmt is not None and fmt < 2):
        f.block(f"{sname}: {path}", f"prefer: is v2+ only (format is v{fmt})")
    if entry.get("mutable") is True:
        has = any(isinstance(entry.get(k), str) and entry.get(k) != "" for k in ("text", "symlink", "copy"))
        if not has:
            f.warn(f"{sname}: {path}", "mutable path needs text/symlink/copy (nothing to mutate otherwise)")
    arch = entry.get("arch")
    archs = [arch] if isinstance(arch, str) else arch if isinstance(arch, list) else None
    if archs is not None:
        bad = [a for a in archs if a not in VALID_ARCHES]
        if bad:
            f.warn(f"{sname}: {path}", f"invalid arch name(s) {bad}: use Debian names {sorted(VALID_ARCHES)}")


def check_v3_essential(doc: Any, fmt: int | None, f: Findings) -> None:
    # v3-essential is a v2-only backport for arch-gated essentials; on v3 use
    # essential-as-map, on v1 plain essential. (mirrors the eval's exact_ok=2.)
    for name, body in slices_of(doc).items():
        if isinstance(body, dict) and "v3-essential" in body and fmt is not None and fmt != 2:
            f.block(f"{name}.v3-essential", f"v3-essential is a v2 backport field (format is v{fmt})")
    if isinstance(doc.get("essential"), dict) and fmt is not None and fmt < 3:
        f.block("essential:", f"essential-as-map is v3+ only (format is v{fmt})")
    for name, body in slices_of(doc).items():
        ess = body.get("essential") if isinstance(body, dict) else None
        if isinstance(ess, dict) and fmt is not None and fmt < 3:
            f.block(f"{name}.essential", f"essential-as-map is v3+ only (format is v{fmt})")


def detect_format(argv_fmt: int | None, argv_branch: str | None) -> int | None:
    if argv_fmt is not None:
        return argv_fmt
    if argv_branch:
        return BRANCH_FORMAT.get(argv_branch)
    cy = Path("chisel.yaml")
    if cy.exists():
        try:
            doc = yaml.safe_load(cy.read_text(encoding="utf-8"))
            v = str(doc.get("format", "")) if isinstance(doc, dict) else ""
            m = re.search(r"(\d+)", v)
            if m:
                return int(m.group(1))
        except (yaml.YAMLError, OSError):
            pass
    return None


def check_file(path: Path, fmt: int | None) -> Findings:
    f = Findings(str(path))
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        f.block("", f"cannot read: {e}")
        return f
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as e:
        f.block("", f"YAML parse error: {str(e).splitlines()[0]}")
        return f
    if not isinstance(doc, dict):
        f.block("", "top level is not a mapping")
        return f
    check_filename(doc, path, f)
    check_essential_sorted(doc, f)
    check_slices(doc, fmt, f)
    check_v3_essential(doc, fmt, f)
    if fmt is None:
        f.info("", "format unknown: version-gated checks (hint/prefer/v3-essential/essential-map) skipped -- pass --format or --branch")
    return f


def main(argv: list[str]) -> int:
    files: list[str] = []
    fmt_arg: int | None = None
    branch_arg: str | None = None
    it = iter(argv)
    for a in it:
        if a == "--format":
            fmt_arg = int(next(it))
        elif a.startswith("--format="):
            fmt_arg = int(a.split("=", 1)[1])
        elif a == "--branch":
            branch_arg = next(it)
        elif a.startswith("--branch="):
            branch_arg = a.split("=", 1)[1]
        elif a in ("-h", "--help"):
            print(__doc__)
            return 0
        else:
            files.append(a)
    if not files:
        print("usage: check-slice.py <slice.yaml> [...] [--format N | --branch NAME]", file=sys.stderr)
        return 2

    fmt = detect_format(fmt_arg, branch_arg)
    had_block = False
    total = 0
    for name in files:
        f = check_file(Path(name), fmt)
        for sev, where, msg in f.rows:
            total += 1
            had_block = had_block or sev == "block"
            loc = f"{f.file}: {where}: " if where else f"{f.file}: "
            print(f"{sev:5}  {loc}{msg}")
    if total == 0:
        print(f"ok: {len(files)} file(s) clean" + (f" (format v{fmt})" if fmt else ""))
    return 1 if had_block else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
