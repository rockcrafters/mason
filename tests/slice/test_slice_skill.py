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
