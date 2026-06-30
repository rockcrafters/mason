#!/usr/bin/env python3
"""mason slice scorers for pats. one function per scorer; dispatch on argv[1]
(the scorer id, passed by scorers/run.sh as $PATS_SCORER). each prints a single
float in [0,1].

a scorer receives the whole run output dir (env PATS_OUTPUT_DIR) and scores
whatever's there. the dir holds, per *target* (a sliced package):

    <target>.yaml           the slice the agent produced
    <target>.expected.yaml  ground truth (knockout snapshot or denovo silver)

plus per *case* (env PATS_TASK):

    <case>.task.yaml        the spread test task.yaml the agent wrote (if any)
    <case>.spread.txt       concatenated spread-test bundle text (if any)
    <case>.branch           the chisel-releases branch (format-version checks)

the *targets* are the stems of the `*.expected.yaml` files. single-target cases
have exactly one; multi-target (denovo) cases have several. per-target scorers
average across targets, so single-target is just the N=1 case.

ported + generalised from the old tests/slice/test_slice_skill.py.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any, Callable

import yaml

OUT = Path(os.environ["PATS_OUTPUT_DIR"])
TASK = os.environ["PATS_TASK"]  # the case id (also the single-target package)

_EXP_SUFFIX = ".expected.yaml"


def _targets() -> list[str]:
    """stems with a ground-truth file -- the set of packages that should exist."""
    ts = sorted(p.name[: -len(_EXP_SUFFIX)] for p in OUT.glob("*" + _EXP_SUFFIX))
    return ts or [TASK]  # fallback so a missing-expected run still scores (-> 0s)


def _avg(fn: Callable[[str], float]) -> float:
    ts = _targets()
    vals = [fn(t) for t in ts]
    return sum(vals) / len(vals) if vals else 1.0


def _load(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return None


def _produced(t: str) -> Any:
    return _load(OUT / f"{t}.yaml")


def _expected(t: str) -> Any:
    return _load(OUT / f"{t}{_EXP_SUFFIX}")


def _branch() -> str | None:
    f = OUT / f"{TASK}.branch"
    return f.read_text(encoding="utf-8").strip() if f.exists() else None


_BRANCH_FORMAT = {
    "ubuntu-20.04": 1, "ubuntu-22.04": 1, "ubuntu-24.04": 1,
    "ubuntu-25.10": 2, "ubuntu-26.04": 3,
}


def _fmt() -> int | None:
    return _BRANCH_FORMAT.get(_branch() or "")


_CANONICAL = {
    "bins", "libs", "config", "configs", "data", "scripts", "copyright",
    "core", "standard", "var", "headers", "jars", "license", "notice",
    "locales", "services", "modules", "tables", "chisel",
}
_BIN_DIRS = ("/usr/bin/", "/usr/sbin/", "/bin/", "/sbin/", "/usr/libexec/")


def _iter_contents(doc: Any):
    if not isinstance(doc, dict):
        return
    slices = doc.get("slices")
    if not isinstance(slices, dict):
        return
    for sname, body in slices.items():
        if not isinstance(body, dict):
            continue
        contents = body.get("contents")
        if not isinstance(contents, dict):
            continue
        for path, entry in contents.items():
            yield sname, path, entry


def _iter_bodies(doc: Any):
    if not isinstance(doc, dict):
        return
    slices = doc.get("slices")
    if not isinstance(slices, dict):
        return
    for name, body in slices.items():
        if isinstance(body, dict):
            yield name, body


def _mutate_map(doc: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    for name, body in _iter_bodies(doc):
        m = body.get("mutate")
        if isinstance(m, str) and m.strip():
            out[name] = m
    return out


def _mutate_paths(script: str) -> set[str]:
    return set(re.findall(r'content\.(?:read|write)\s*\(\s*["\']([^"\']+)["\']', script))


def _content_paths(doc: Any) -> set[str]:
    return {str(p).lower() for _, p, _ in _iter_contents(doc)}


def _declared_binaries(doc: Any) -> set[str]:
    out: set[str] = set()
    for _, path, _ in _iter_contents(doc):
        if not any(path.startswith(d) for d in _BIN_DIRS):
            continue
        if path.endswith("/") or "*" in path or "?" in path:
            continue
        out.add(path.rsplit("/", 1)[-1])
    return out


# --- per-target scorers (averaged across targets via _avg) -------------------

def target_present() -> float:
    return _avg(lambda t: 1.0 if (OUT / f"{t}.yaml").exists() and (OUT / f"{t}.yaml").stat().st_size > 0 else 0.0)


def yaml_parses() -> float:
    return _avg(lambda t: 1.0 if _produced(t) is not None else 0.0)


def filename_matches_package() -> float:
    def f(t: str) -> float:
        doc = _produced(t)
        return 1.0 if isinstance(doc, dict) and doc.get("package") == t else 0.0
    return _avg(f)


def paths_sorted() -> float:
    def f(t: str) -> float:
        doc = _produced(t)
        if not isinstance(doc, dict):
            return 0.0
        slices = doc.get("slices")
        if not isinstance(slices, dict):
            return 1.0
        for body in slices.values():
            if not isinstance(body, dict):
                continue
            contents = body.get("contents")
            if not isinstance(contents, dict):
                continue
            keys = list(contents.keys())
            if keys != sorted(keys):
                return 0.0
        return 1.0
    return _avg(f)


def copyright_essential() -> float:
    def f(t: str) -> float:
        doc = _produced(t)
        if not isinstance(doc, dict):
            return 0.0
        pkg = doc.get("package")
        essential = doc.get("essential")
        if not isinstance(essential, list) or not isinstance(pkg, str):
            slices = doc.get("slices") or {}
            return 1.0 if isinstance(slices, dict) and "copyright" in slices else 0.0
        return 1.0 if f"{pkg}_copyright" in essential else 0.0
    return _avg(f)


def copyright_path_present() -> float:
    def f(t: str) -> float:
        doc = _produced(t)
        if not isinstance(doc, dict):
            return 0.0
        pkg = doc.get("package") if isinstance(doc.get("package"), str) else t
        slices = doc.get("slices")
        if not isinstance(slices, dict):
            return 0.0
        cp = slices.get("copyright")
        if not isinstance(cp, dict):
            return 0.0
        contents = cp.get("contents")
        if not isinstance(contents, dict):
            return 0.0
        return 1.0 if f"/usr/share/doc/{pkg}/copyright" in contents else 0.0
    return _avg(f)


def arch_format() -> float:
    def f(t: str) -> float:
        p = OUT / f"{t}.yaml"
        if not p.exists():
            return 0.0
        bad = total = 0
        for raw in p.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line.startswith("arch:"):
                continue
            total += 1
            value = line[len("arch:"):].strip()
            if value.startswith("[") and value.endswith("]"):
                inner = value[1:-1]
                if inner != inner.strip():
                    bad += 1
                    continue
                parts = [x.strip() for x in inner.split(",")]
                if parts != sorted(parts) or any(x != x.lower() for x in parts):
                    bad += 1
        return 1.0 if total == 0 else (total - bad) / total
    return _avg(f)


def _path_penalty(matches: Callable[[str], bool], allow: Callable[[str, Any], bool] = lambda p, d: False) -> Callable[[str], float]:
    def f(t: str) -> float:
        doc = _produced(t)
        if not isinstance(doc, dict):
            return 0.0
        total = bad = 0
        for _, path, _ in _iter_contents(doc):
            total += 1
            if allow(path, doc):
                continue
            if matches(path):
                bad += 1
        return 1.0 if total == 0 else (total - bad) / total
    return f


def no_man_pages() -> float:
    return _avg(_path_penalty(lambda p: p.startswith("/usr/share/man/") or p.startswith("/usr/man/")))


def no_doc_clutter() -> float:
    def allow(path: str, doc: Any) -> bool:
        pkg = doc.get("package") if isinstance(doc.get("package"), str) else ""
        return path == f"/usr/share/doc/{pkg}/copyright"
    return _avg(_path_penalty(
        lambda p: p.startswith("/usr/share/doc/") or p.startswith("/usr/share/doc-base/") or p.startswith("/usr/share/lintian/"),
        allow,
    ))


def no_shell_completions() -> float:
    pre = ("/usr/share/bash-completion/", "/usr/share/fish/", "/usr/share/zsh/", "/etc/bash_completion.d/")
    return _avg(_path_penalty(lambda p: any(p.startswith(x) for x in pre)))


def mutable_has_text() -> float:
    def f(t: str) -> float:
        doc = _produced(t)
        if not isinstance(doc, dict):
            return 0.0
        total = bad = 0
        for _, _, entry in _iter_contents(doc):
            if not isinstance(entry, dict) or entry.get("mutable") is not True:
                continue
            total += 1
            text = entry.get("text")
            if isinstance(text, str) and text != "":
                continue
            if isinstance(entry.get("symlink"), str) or isinstance(entry.get("copy"), str):
                continue
            bad += 1
        return 1.0 if total == 0 else (total - bad) / total
    return _avg(f)


def slice_names_canonical() -> float:
    def f(t: str) -> float:
        doc = _produced(t)
        if not isinstance(doc, dict):
            return 0.0
        slices = doc.get("slices")
        if not isinstance(slices, dict) or not slices:
            return 1.0
        ok = 0
        for name in slices:
            if not isinstance(name, str):
                continue
            if name in _CANONICAL:
                ok += 1
                continue
            parts = name.split("-")
            if len(parts) >= 2 and (parts[-1] in _CANONICAL or parts[0] in _CANONICAL):
                ok += 1
        return ok / len(slices)
    return _avg(f)


# --- per-target comparison scorers (produced vs expected) --------------------

def mutate_present() -> float:
    def f(t: str) -> float:
        exp = _mutate_map(_expected(t))
        if not exp:
            return 1.0
        act = _mutate_map(_produced(t))
        return sum(1 for name in exp if name in act) / len(exp)
    return _avg(f)


def mutate_paths() -> float:
    def f(t: str) -> float:
        exp_map = _mutate_map(_expected(t))
        if not exp_map:
            return 1.0
        act_map = _mutate_map(_produced(t))
        exp_paths = set().union(*(_mutate_paths(s) for s in exp_map.values()))
        act_paths = set().union(*(_mutate_paths(s) for s in act_map.values())) if act_map else set()
        if not exp_paths and not act_paths:
            return 1.0
        union = exp_paths | act_paths
        return len(exp_paths & act_paths) / len(union) if union else 0.0
    return _avg(f)


def slice_count_not_inflated() -> float:
    def f(t: str) -> float:
        actual, expected = _produced(t), _expected(t)
        if not isinstance(actual, dict) or not isinstance(expected, dict):
            return 0.0
        a = actual.get("slices") or {}
        e = expected.get("slices") or {}
        if not isinstance(a, dict) or not isinstance(e, dict):
            return 0.0
        na, ne = len(a), len(e)
        if na == 0:
            return 1.0 if ne == 0 else 0.0
        return min(1.0, ne / na)
    return _avg(f)


def structural_distance() -> float:
    def f(t: str) -> float:
        actual, expected = _produced(t), _expected(t)
        if actual is None or expected is None:
            return 0.0
        a, e = _content_paths(actual), _content_paths(expected)
        if not a and not e:
            return 1.0
        union = a | e
        return len(a & e) / len(union) if union else 0.0
    return _avg(f)


# --- format-version compatibility (branch-gated, per target) -----------------

def _fmt_compat(uses: Callable[[Any], bool], min_ok_fmt: int, exact_ok: int | None = None) -> float:
    fmt = _fmt()
    if fmt is None:
        return 1.0

    def f(t: str) -> float:
        doc = _produced(t)
        if not isinstance(doc, dict):
            return 0.0
        if fmt >= min_ok_fmt or (exact_ok is not None and fmt == exact_ok):
            return 1.0
        return 0.0 if uses(doc) else 1.0
    return _avg(f)


def v3_essential_format_compat() -> float:
    return _fmt_compat(lambda d: any("v3-essential" in b for _, b in _iter_bodies(d)), min_ok_fmt=99, exact_ok=2)


def essential_map_format_compat() -> float:
    def uses(d: Any) -> bool:
        return isinstance(d.get("essential"), dict) or any(isinstance(b.get("essential"), dict) for _, b in _iter_bodies(d))
    return _fmt_compat(uses, min_ok_fmt=3)


def hint_format_compat() -> float:
    return _fmt_compat(lambda d: any("hint" in b for _, b in _iter_bodies(d)), min_ok_fmt=3)


def prefer_format_compat() -> float:
    def uses(d: Any) -> bool:
        for _, body in _iter_bodies(d):
            contents = body.get("contents")
            if isinstance(contents, dict) and any(isinstance(o, dict) and "prefer" in o for o in contents.values()):
                return True
        return False
    return _fmt_compat(uses, min_ok_fmt=2)


def essential_list_on_v1() -> float:
    fmt = _fmt()
    if fmt is None or fmt != 1:
        return 1.0

    def f(t: str) -> float:
        doc = _produced(t)
        if not isinstance(doc, dict):
            return 0.0
        for _, body in _iter_bodies(doc):
            ess = body.get("essential")
            if ess is None:
                continue
            if not isinstance(ess, list) or not all(isinstance(x, str) for x in ess):
                return 0.0
        return 1.0
    return _avg(f)


# --- case-level scorers (spread tests; one bundle per case) ------------------

def spread_test_present() -> float:
    p = OUT / f"{TASK}.task.yaml"
    return 1.0 if p.exists() and p.stat().st_size > 0 else 0.0


def spread_exercises_binaries() -> float:
    # union of binaries across all produced target slices vs the spread bundle.
    bins: set[str] = set()
    for t in _targets():
        bins |= _declared_binaries(_produced(t))
    if not bins:
        return 1.0
    bundle_path = OUT / f"{TASK}.spread.txt"
    bundle = bundle_path.read_text(encoding="utf-8") if bundle_path.exists() else ""
    if not bundle:
        return 0.0
    return sum(1 for b in bins if b in bundle) / len(bins)


SCORERS = {
    "target-present": target_present,
    "yaml-parses": yaml_parses,
    "filename-matches-package": filename_matches_package,
    "paths-sorted": paths_sorted,
    "copyright-essential": copyright_essential,
    "copyright-path-present": copyright_path_present,
    "arch-format": arch_format,
    "mutate-present": mutate_present,
    "mutate-paths": mutate_paths,
    "no-man-pages": no_man_pages,
    "no-doc-clutter": no_doc_clutter,
    "no-shell-completions": no_shell_completions,
    "mutable-has-text": mutable_has_text,
    "slice-count-not-inflated": slice_count_not_inflated,
    "slice-names-canonical": slice_names_canonical,
    "structural-distance": structural_distance,
    "spread-test-present": spread_test_present,
    "spread-exercises-binaries": spread_exercises_binaries,
    "v3-essential-format-compat": v3_essential_format_compat,
    "essential-map-format-compat": essential_map_format_compat,
    "hint-format-compat": hint_format_compat,
    "prefer-format-compat": prefer_format_compat,
    "essential-list-on-v1": essential_list_on_v1,
}


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in SCORERS:
        sys.exit(f"usage: slice_scorers.py <scorer-id>; known: {', '.join(SCORERS)}")
    print(f"{SCORERS[sys.argv[1]]():.4f}")


if __name__ == "__main__":
    main()
