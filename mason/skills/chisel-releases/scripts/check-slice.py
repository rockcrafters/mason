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
(functionality). It only checks the SDF text. yamllint cosmetics (line
length <= 100, blank-line count, indent) are also NOT covered -- CI's lint
job runs yamllint separately.

Usage:
  check-slice.py <slice.yaml> [<slice2.yaml> ...] [--format N | --branch NAME]

Format detection (needed for version-gated fields hint/prefer/v3-essential and
essential-as-map): --format wins, else --branch reads that branch's own
chisel.yaml from the local git object store, else the format: field of
./chisel.yaml, else unknown (gated checks are skipped, noted).

Output: one finding per line, `SEVERITY  file: where: message`.
  block  hard gate -- chisel won't parse it, or CI/lint fails. exit code 1.
  warn   reviewers reliably reject this. exit code stays 0.
  info   nit, or a check skipped because format is unknown.

Exit code is 1 if any block finding, else 0. Stdlib + pyyaml only; runs under
`uv run` (per the shebang) or `python3 check-slice.py` if pyyaml is importable.
"""
from __future__ import annotations

import re
import subprocess
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

# chisel's own slice-name rule (internal/setup: SnameExp) -- no trailing or
# doubled hyphens, which a plain charset class would let through.
SNAME_RE = re.compile(r"^[a-z](?:-?[a-z0-9]){2,}$")

# chisel's SDF filename rule (internal/setup: FnameExp). a non-matching .yaml
# basename fails the whole release parse; a non-.yaml file is silently ignored.
FNAME_RE = re.compile(r"^[a-z0-9](?:-?[.a-z0-9+]){1,}\.yaml$")

# paths a minimal rootfs never needs -- see shared/CHISEL.md "Exclude by Default".
CLUTTER = {
    "man pages": ("/usr/share/man/", "/usr/man/"),
    "shell completions": (
        "/usr/share/bash-completion/", "/usr/share/fish/",
        "/usr/share/zsh/", "/etc/bash_completion.d/",
    ),
    "doc-base/lintian metadata": ("/usr/share/doc-base/", "/usr/share/lintian/"),
}

# legal files that legitimately live under /usr/share/doc alongside copyright
# (not clutter). basename stem, uppercased, after stripping a text/compress suffix.
LEGAL_DOC = {
    "COPYRIGHT", "NOTICE", "LICENSE", "LICENCE", "COPYING",
    "AUTHORS", "THIRDPARTYNOTICES", "THIRD-PARTY-NOTICES",
}


def is_legal_doc(basename: str) -> bool:
    stem = basename
    for suf in (".gz", ".xz", ".bz2", ".txt", ".md", ".rst"):
        if stem.lower().endswith(suf):
            stem = stem[: -len(suf)]
    return stem.upper() in LEGAL_DOC


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
    if path.name.endswith(".yml"):
        f.block("filename", "chisel silently ignores non-.yaml files -- rename to .yaml")
    elif not FNAME_RE.match(path.name):
        f.block("filename", f"'{path.name}' fails chisel's filename rule {FNAME_RE.pattern} (whole-release parse error)")
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

    # copyright: a strong convention, not a CI parse/lint gate (some merged
    # library SDFs skip it), so warn. it ships either the copyright file
    # directly, or the doc dir as a symlink to another package's (shared).
    cp = slices.get("copyright")
    if not isinstance(cp, dict):
        f.warn("slices:", "no copyright slice -- reviewers expect every SDF to ship one")
    elif pkg:
        contents = cp.get("contents") if isinstance(cp.get("contents"), dict) else {}
        docdir = f"/usr/share/doc/{pkg}"
        if not any(k in contents for k in (f"{docdir}/copyright", docdir, docdir + "/")):
            f.warn("copyright", f"ships no copyright ({docdir}/copyright, or the doc dir as a shared-copyright symlink)")
    ess = doc.get("essential")
    if pkg and not (isinstance(ess, list) and f"{pkg}_copyright" in ess) \
            and not (isinstance(ess, dict) and f"{pkg}_copyright" in ess):
        f.warn("essential:", f"{pkg}_copyright not in global essential (so not every slice ships it)")

    for name, body in slices.items():
        if not isinstance(name, str) or not SNAME_RE.match(name):
            f.block(f"slices.{name}", f"slice name must match {SNAME_RE.pattern} (chisel parse error)")
        if not isinstance(body, dict):
            continue
        check_slice_body(name, body, pkg, fmt, f)


# validate-hints allows only these chars; chisel core caps length at 40 and
# rejects non-printable. see shared/CHISEL.md "hint: style".
_HINT_ALLOWED = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .,;()")


def check_hint(name: str, hint: Any, f: Findings) -> None:
    if not isinstance(hint, str):
        return
    where = f"{name}.hint"
    # chisel core (parse errors):
    if len(hint) > 40:
        f.block(where, f"hint is {len(hint)} chars -- chisel caps it at 40 (parse error)")
    if "\n" in hint or any(not c.isprintable() for c in hint):
        f.block(where, "hint must be a single line of printable chars (parse error)")
    # validate-hints CI style (noun phrase; the finite-verb rule needs NLP, skipped):
    if hint[:1].islower():
        f.warn(where, "hint should be sentence case (capitalise the first letter)")
    if re.match(r"(?i)^(a|an|the)\b", hint):
        f.warn(where, "hint should not start with an article (a/an/the)")
    if hint[-1:] in {".", ",", ";", ":", "!"}:
        f.warn(where, "hint should not end with punctuation")
    if "  " in hint or hint != hint.strip():
        f.warn(where, "hint should have no double, leading, or trailing spaces")
    stray = sorted(set(hint) - _HINT_ALLOWED - {"\n"})
    if stray:
        f.warn(where, f"hint has chars outside validate-hints' set {stray}; allowed: letters, digits, space, . , ; ( )")


def check_slice_body(name: str, body: dict, pkg: str, fmt: int | None, f: Findings) -> None:
    if name in BAD_SLICE_NAMES:
        f.warn(f"slices.{name}", f"use '{BAD_SLICE_NAMES[name]}' not '{name}'")

    if "hint" in body:
        if fmt is not None and fmt < 3:
            f.block(f"{name}.hint", f"hint: is v3+ only (format is v{fmt})")
        else:
            check_hint(name, body["hint"], f)

    contents = body.get("contents")
    if not isinstance(contents, dict):
        return
    keys = list(contents.keys())
    if not is_sorted(keys):
        f.block(f"{name}.contents", "contents paths not sorted (bytewise/ASCII)")
    for path, entry in contents.items():
        check_path(name, path, entry, pkg, fmt, f)


def check_path(sname: str, path: Any, entry: Any, pkg: str, fmt: int | None, f: Findings) -> None:
    if not isinstance(path, str) or not path.startswith("/"):
        f.block(f"{sname}: {path}", "path must be absolute (start with /)")
        return
    for label, prefixes in CLUTTER.items():
        if any(path.startswith(p) for p in prefixes):
            f.warn(f"{sname}: {path}", f"{label} not shipped in minimal rootfs")
    if path.startswith("/usr/share/doc/"):
        docdir = f"/usr/share/doc/{pkg}"
        base = path.rstrip("/").rsplit("/", 1)[-1]
        # exempt the package's own doc dir (shared-copyright symlink) and legal files.
        if pkg and path.rstrip("/") != docdir and not is_legal_doc(base):
            f.warn(f"{sname}: {path}", "doc clutter: ship only the copyright/notice/licence files")

    if not isinstance(entry, dict):
        return
    if "prefer" in entry and (fmt is not None and fmt < 2):
        f.block(f"{sname}: {path}", f"prefer: is v2+ only (format is v{fmt})")
    arch = entry.get("arch")
    archs = [arch] if isinstance(arch, str) else arch if isinstance(arch, list) else None
    if archs is not None:
        bad = [a for a in archs if a not in VALID_ARCHES]
        if bad:
            f.block(f"{sname}: {path}", f"invalid arch name(s) {bad}: use Debian names {sorted(VALID_ARCHES)} (chisel parse error)")


def check_v3_essential(doc: Any, fmt: int | None, f: Findings) -> None:
    # essential shape is format-gated both ways: map on v1/v2 is a parse error,
    # list on v3 is a parse error ("essential expects a map"). v3-essential is
    # the pre-v3 backport (needs chisel>=1.3.0): valid on v1/v2, a hard parse
    # error on v3 (top-level or per-slice).
    if fmt is None:
        return
    if "v3-essential" in doc and fmt >= 3:
        f.block("v3-essential:", f"v3-essential is rejected on v3 (chisel parse error) -- fold into the essential: map (format is v{fmt})")
    if isinstance(doc.get("essential"), dict) and fmt < 3:
        f.block("essential:", f"essential-as-map is v3+ only (format is v{fmt})")
    if isinstance(doc.get("essential"), list) and fmt >= 3:
        f.block("essential:", f"essential must be a map on v3 (chisel parse error: 'essential expects a map'; format is v{fmt})")
    for name, body in slices_of(doc).items():
        if not isinstance(body, dict):
            continue
        if "v3-essential" in body and fmt >= 3:
            f.block(f"{name}.v3-essential", f"v3-essential is rejected on v3 (chisel parse error) -- fold into the essential: map (format is v{fmt})")
        ess = body.get("essential")
        if isinstance(ess, dict) and fmt < 3:
            f.block(f"{name}.essential", f"essential-as-map is v3+ only (format is v{fmt})")
        elif isinstance(ess, list) and fmt >= 3:
            f.block(f"{name}.essential", f"essential must be a map on v3 (chisel parse error: 'essential expects a map'; format is v{fmt})")


def format_of_branch(branch: str) -> int | None:
    """Resolve a branch's format from *its own* chisel.yaml, read out of the local
    git object store -- no hardcoded branch->format table, no network. A static
    linter stays offline and deterministic: `git show <ref>:chisel.yaml`, trying
    the local ref then origin/<ref> (in a fresh clone the target release is often
    only a remote-tracking ref, which is exactly the cross-branch case --branch
    serves). None if the ref/file/format can't be found -- callers treat unknown
    format by skipping the version-gated checks. Pass --format N to force it."""
    for ref in (branch, f"origin/{branch}"):
        try:
            r = subprocess.run(
                ["git", "show", f"{ref}:chisel.yaml"],
                capture_output=True, text=True, timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if r.returncode == 0:
            m = re.search(r"^format:\s*\"?v?(\d+)", r.stdout, re.M)
            return int(m.group(1)) if m else None
    return None


def detect_format(argv_fmt: int | None, argv_branch: str | None) -> int | None:
    if argv_fmt is not None:
        return argv_fmt
    if argv_branch:
        return format_of_branch(argv_branch)
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


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader that errors on duplicate mapping keys (safe_load keeps the
    last one silently, so a pasted-twice contents path is invisible to it --
    but CI's yamllint fails on it)."""


def _no_dup_keys(loader, node, deep=False):
    seen = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in seen:
            raise yaml.YAMLError(f"duplicate mapping key {key!r} (line {key_node.start_mark.line + 1})")
        seen.add(key)
    return yaml.SafeLoader.construct_mapping(loader, node, deep)


_StrictLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_dup_keys)


def check_file(path: Path, fmt: int | None) -> Findings:
    f = Findings(str(path))
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        f.block("", f"cannot read: {e}")
        return f
    try:
        doc = yaml.load(text, Loader=_StrictLoader)
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
        f.info("", "format unknown: version-gated checks (hint/prefer/v3-essential/essential-map) skipped -- run inside the target checkout, or pass --format N")
    return f


def main(argv: list[str]) -> int:
    files: list[str] = []
    fmt_arg: int | None = None
    branch_arg: str | None = None
    def parse_fmt(value: str) -> int:
        # accept "3", "v3", "chisel-v3" -- orientation prints "v1"-style strings.
        m = re.search(r"(\d+)", value)
        if not m:
            print(f"check-slice.py: bad --format value {value!r}", file=sys.stderr)
            print("usage: check-slice.py <slice.yaml> [...] [--format N | --branch NAME]", file=sys.stderr)
            raise SystemExit(2)
        return int(m.group(1))

    it = iter(argv)
    for a in it:
        if a in ("--format", "--branch"):
            value = next(it, None)
            if value is None:
                print(f"check-slice.py: {a} needs a value", file=sys.stderr)
                return 2
            if a == "--format":
                fmt_arg = parse_fmt(value)
            else:
                branch_arg = value
        elif a.startswith("--format="):
            fmt_arg = parse_fmt(a.split("=", 1)[1])
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
