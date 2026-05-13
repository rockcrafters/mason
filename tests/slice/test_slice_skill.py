"""scored eval for slice skill. operates on cached runs in .cache/runs/.
generate runs first via `make run`; this file only scores.

scorers inlined here -- one function per test, no indirection.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from framework import scored


def _load_yaml(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return None


@scored
def test_target_present(run) -> float:
    """Did the agent produce a file for this target at all? Runs even when
    the file is missing (no skip), so scoring captures cascade-completeness
    for multi-target cases."""
    return 1.0 if run.result_path.exists() and run.result_path.stat().st_size > 0 else 0.0


@scored
def test_yaml_parses(agent_output) -> float:
    return 1.0 if _load_yaml(agent_output.slice_path) is not None else 0.0


@scored
def test_filename_matches_package(agent_output) -> float:
    doc = _load_yaml(agent_output.slice_path)
    if not isinstance(doc, dict):
        return 0.0
    return 1.0 if doc.get("package") == agent_output.slice_path.stem else 0.0


@scored
def test_paths_sorted(agent_output) -> float:
    doc = _load_yaml(agent_output.slice_path)
    if not isinstance(doc, dict):
        return 0.0
    slices = doc.get("slices")
    if not isinstance(slices, dict):
        return 1.0
    total = 0
    ok = 0
    for body in slices.values():
        if not isinstance(body, dict):
            continue
        contents = body.get("contents")
        if not isinstance(contents, dict):
            continue
        keys = list(contents.keys())
        total += 1
        if keys == sorted(keys):
            ok += 1
    if total == 0:
        return 1.0
    return ok / total


@scored
def test_copyright_essential(agent_output) -> float:
    doc = _load_yaml(agent_output.slice_path)
    if not isinstance(doc, dict):
        return 0.0
    pkg = doc.get("package")
    essential = doc.get("essential")
    if not isinstance(essential, list) or not isinstance(pkg, str):
        slices = doc.get("slices") or {}
        return 1.0 if isinstance(slices, dict) and "copyright" in slices else 0.0
    return 1.0 if f"{pkg}_copyright" in essential else 0.0


@scored
def test_arch_format(agent_output) -> float:
    p = agent_output.slice_path
    if not p.exists():
        return 0.0
    bad = 0
    total = 0
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
            if parts != sorted(parts):
                bad += 1
                continue
            if any(x != x.lower() for x in parts):
                bad += 1
    if total == 0:
        return 1.0
    return (total - bad) / total


def _mutate_map(doc: Any) -> dict[str, str]:
    if not isinstance(doc, dict):
        return {}
    slices = doc.get("slices")
    if not isinstance(slices, dict):
        return {}
    out: dict[str, str] = {}
    for name, body in slices.items():
        if isinstance(body, dict):
            m = body.get("mutate")
            if isinstance(m, str) and m.strip():
                out[name] = m
    return out


def _token_similarity(a: str, b: str) -> float:
    import re
    ta = set(re.findall(r"\w+|[^\s\w]", a))
    tb = set(re.findall(r"\w+|[^\s\w]", b))
    if not ta and not tb:
        return 1.0
    union = ta | tb
    return len(ta & tb) / len(union) if union else 0.0


@scored
def test_mutate_similarity(agent_output) -> float:
    """for each slice with mutate in expected, score token-similarity of actual's mutate (0 if absent). avg over expected mutate-slices."""
    actual = _load_yaml(agent_output.slice_path)
    try:
        expected = yaml.safe_load(agent_output.expected_yaml)
    except yaml.YAMLError:
        expected = None
    exp = _mutate_map(expected)
    if not exp:
        return 1.0
    act = _mutate_map(actual)
    return sum(_token_similarity(v, act.get(name, "")) for name, v in exp.items()) / len(exp)


@scored
def test_no_man_pages(agent_output) -> float:
    """man pages never belong in slices. 1.0 if none, else fraction of content paths that are not man."""
    doc = _load_yaml(agent_output.slice_path)
    if not isinstance(doc, dict):
        return 0.0
    slices = doc.get("slices")
    if not isinstance(slices, dict):
        return 1.0
    total = 0
    bad = 0
    for body in slices.values():
        if not isinstance(body, dict):
            continue
        contents = body.get("contents")
        if not isinstance(contents, dict):
            continue
        for path in contents:
            total += 1
            if path.startswith("/usr/share/man/") or path.startswith("/usr/man/"):
                bad += 1
    if total == 0:
        return 1.0
    return (total - bad) / total


def _iter_contents(doc: Any):
    """yield (slice_name, path, entry) for every contents path."""
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


_CANONICAL_SLICE_NAMES = {
    "bins", "libs", "config", "configs", "data", "scripts", "copyright",
    "core", "standard", "var", "headers", "jars", "license", "notice",
    "locales", "services", "modules", "tables", "chisel",
}


@scored
def test_no_doc_clutter(agent_output) -> float:
    """penalise /usr/share/doc/** (except <pkg>/copyright), /usr/share/doc-base/**, /usr/share/lintian/**."""
    doc = _load_yaml(agent_output.slice_path)
    if not isinstance(doc, dict):
        return 0.0
    pkg = doc.get("package") if isinstance(doc.get("package"), str) else agent_output.slice_path.stem
    allowed_copyright = f"/usr/share/doc/{pkg}/copyright"
    total = 0
    bad = 0
    for _, path, _ in _iter_contents(doc):
        total += 1
        if path == allowed_copyright:
            continue
        if path.startswith("/usr/share/doc/") or path.startswith("/usr/share/doc-base/") or path.startswith("/usr/share/lintian/"):
            bad += 1
    if total == 0:
        return 1.0
    return (total - bad) / total


@scored
def test_no_shell_completions(agent_output) -> float:
    """penalise shell completion paths -- rarely belong in slices."""
    doc = _load_yaml(agent_output.slice_path)
    if not isinstance(doc, dict):
        return 0.0
    prefixes = ("/usr/share/bash-completion/", "/usr/share/fish/", "/usr/share/zsh/", "/etc/bash_completion.d/")
    total = 0
    bad = 0
    for _, path, _ in _iter_contents(doc):
        total += 1
        if any(path.startswith(p) for p in prefixes):
            bad += 1
    if total == 0:
        return 1.0
    return (total - bad) / total


@scored
def test_mutable_has_text(agent_output) -> float:
    """paths with mutable: true must have a non-empty text: companion (or symlink/copy)."""
    doc = _load_yaml(agent_output.slice_path)
    if not isinstance(doc, dict):
        return 0.0
    total = 0
    bad = 0
    for _, _, entry in _iter_contents(doc):
        if not isinstance(entry, dict):
            continue
        if entry.get("mutable") is not True:
            continue
        total += 1
        text = entry.get("text")
        if isinstance(text, str) and text != "":
            continue
        if isinstance(entry.get("symlink"), str) or isinstance(entry.get("copy"), str):
            continue
        bad += 1
    if total == 0:
        return 1.0
    return (total - bad) / total


@scored
def test_slice_count_not_inflated(agent_output) -> float:
    """penalise overshipping slices. score = min(1, expected_count / actual_count)."""
    actual = _load_yaml(agent_output.slice_path)
    try:
        expected = yaml.safe_load(agent_output.expected_yaml)
    except yaml.YAMLError:
        expected = None
    if not isinstance(actual, dict) or not isinstance(expected, dict):
        return 0.0
    a = actual.get("slices") or {}
    e = expected.get("slices") or {}
    if not isinstance(a, dict) or not isinstance(e, dict):
        return 0.0
    na = len(a)
    ne = len(e)
    if na == 0:
        return 1.0 if ne == 0 else 0.0
    return min(1.0, ne / na)


@scored
def test_slice_names_canonical(agent_output) -> float:
    """slice names should be canonical or <word>-<canonical> patterns."""
    doc = _load_yaml(agent_output.slice_path)
    if not isinstance(doc, dict):
        return 0.0
    slices = doc.get("slices")
    if not isinstance(slices, dict) or not slices:
        return 1.0
    ok = 0
    for name in slices:
        if not isinstance(name, str):
            continue
        if name in _CANONICAL_SLICE_NAMES:
            ok += 1
            continue
        parts = name.split("-")
        if len(parts) >= 2 and parts[-1] in _CANONICAL_SLICE_NAMES:
            ok += 1
            continue
        if parts[0] in _CANONICAL_SLICE_NAMES and len(parts) >= 2:
            ok += 1
    return ok / len(slices)


@scored
def test_copyright_path_present(agent_output) -> float:
    """copyright slice must contain /usr/share/doc/<pkg>/copyright."""
    doc = _load_yaml(agent_output.slice_path)
    if not isinstance(doc, dict):
        return 0.0
    pkg = doc.get("package") if isinstance(doc.get("package"), str) else agent_output.slice_path.stem
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


def _normalise(doc: Any) -> Any:
    if isinstance(doc, dict):
        return {k: _normalise(v) for k, v in sorted(doc.items())}
    if isinstance(doc, list):
        return sorted(
            (_normalise(x) for x in doc),
            key=lambda x: yaml.safe_dump(x, sort_keys=True),
        )
    return doc


def _flatten(doc: Any, prefix: str = "") -> set[str]:
    out: set[str] = set()
    if isinstance(doc, dict):
        for k, v in doc.items():
            out |= _flatten(v, f"{prefix}/{k}")
    elif isinstance(doc, list):
        for i, v in enumerate(doc):
            out |= _flatten(v, f"{prefix}[{i}]")
    else:
        out.add(f"{prefix}={doc!r}")
    return out


# chisel.yaml format version per release branch. derived from current
# canonical/chisel-releases state. v1: flat essential list only.
# v2: + `v3-essential:` map, + `prefer:`. v3: essential-as-map (arch-gated),
# + `hint:`, drops `v3-essential:` (folded into `essential:`).
_BRANCH_FORMAT = {
    "ubuntu-20.04": 1,
    "ubuntu-22.04": 1,
    "ubuntu-24.04": 1,
    "ubuntu-25.10": 2,
    "ubuntu-26.04": 3,
}


def _branch_format(run) -> int | None:
    return _BRANCH_FORMAT.get(run.case.branch)


def _iter_slice_bodies(doc: Any):
    if not isinstance(doc, dict):
        return
    slices = doc.get("slices")
    if not isinstance(slices, dict):
        return
    for name, body in slices.items():
        if isinstance(body, dict):
            yield name, body


@scored
def test_v3_essential_format_compat(agent_output) -> float:
    """`v3-essential:` is only valid on chisel.yaml format v2 branches.
    On v3 branches the arch-gated map form goes under `essential:` directly.
    On v1 branches `v3-essential:` is unknown."""
    fmt = _branch_format(agent_output)
    if fmt is None:
        return 1.0
    doc = _load_yaml(agent_output.slice_path)
    if not isinstance(doc, dict):
        return 0.0
    uses_v3e = any("v3-essential" in body for _, body in _iter_slice_bodies(doc))
    if fmt == 2:
        return 1.0
    return 0.0 if uses_v3e else 1.0


@scored
def test_essential_map_format_compat(agent_output) -> float:
    """`essential:` as a map (with per-entry options like `{arch: [...]}`)
    is v3-only. On v1/v2 `essential:` must be a flat list of strings."""
    fmt = _branch_format(agent_output)
    if fmt is None:
        return 1.0
    doc = _load_yaml(agent_output.slice_path)
    if not isinstance(doc, dict):
        return 0.0
    map_seen = False
    if isinstance(doc.get("essential"), dict):
        map_seen = True
    for _, body in _iter_slice_bodies(doc):
        if isinstance(body.get("essential"), dict):
            map_seen = True
            break
    if fmt >= 3:
        return 1.0
    return 0.0 if map_seen else 1.0


@scored
def test_hint_format_compat(agent_output) -> float:
    """`hint:` on a slice body is v3-only."""
    fmt = _branch_format(agent_output)
    if fmt is None:
        return 1.0
    doc = _load_yaml(agent_output.slice_path)
    if not isinstance(doc, dict):
        return 0.0
    has_hint = any("hint" in body for _, body in _iter_slice_bodies(doc))
    if fmt >= 3:
        return 1.0
    return 0.0 if has_hint else 1.0


@scored
def test_prefer_format_compat(agent_output) -> float:
    """`prefer:` on a content entry is v2+ only."""
    fmt = _branch_format(agent_output)
    if fmt is None:
        return 1.0
    doc = _load_yaml(agent_output.slice_path)
    if not isinstance(doc, dict):
        return 0.0
    has_prefer = False
    for _, body in _iter_slice_bodies(doc):
        contents = body.get("contents")
        if not isinstance(contents, dict):
            continue
        for opts in contents.values():
            if isinstance(opts, dict) and "prefer" in opts:
                has_prefer = True
                break
        if has_prefer:
            break
    if fmt >= 2:
        return 1.0
    return 0.0 if has_prefer else 1.0


@scored
def test_essential_list_on_v1(agent_output) -> float:
    """On v1 branches per-slice `essential:` must be a flat list of strings,
    not a map. Catches v3-style entries written against an old branch."""
    fmt = _branch_format(agent_output)
    if fmt is None or fmt != 1:
        return 1.0
    doc = _load_yaml(agent_output.slice_path)
    if not isinstance(doc, dict):
        return 0.0
    for _, body in _iter_slice_bodies(doc):
        ess = body.get("essential")
        if ess is None:
            continue
        if not isinstance(ess, list):
            return 0.0
        if not all(isinstance(x, str) for x in ess):
            return 0.0
    return 1.0


@scored
def test_structural_distance(agent_output) -> float:
    actual = _load_yaml(agent_output.slice_path)
    try:
        expected = yaml.safe_load(agent_output.expected_yaml)
    except yaml.YAMLError:
        expected = None
    if actual is None or expected is None:
        return 0.0
    a = _flatten(_normalise(actual))
    e = _flatten(_normalise(expected))
    if not a and not e:
        return 1.0
    union = len(a | e)
    return len(a & e) / union if union else 0.0
