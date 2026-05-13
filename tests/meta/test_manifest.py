"""Tests for manifest loading + case discovery."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from framework.manifest import discover_cases, load_manifest


def test_load_manifest_basic(tmp_path: Path) -> None:
    raw = {
        "chisel_releases": {"url": "u", "sha": "HEAD", "branch": "ubuntu-26.04"},
        "effort": "low",
        "backend": "claude",
        "models": [
            {"id": "claude-haiku-4-5-20251001"},
            {"id": "claude-sonnet-4-6", "effort": "medium"},
        ],
        "timeout_seconds": 600,
        "stuck_timeout_seconds": 300,
    }
    p = tmp_path / "manifest.yaml"
    p.write_text(yaml.safe_dump(raw), encoding="utf-8")
    m = load_manifest(p)
    assert m.chisel_releases_url == "u"
    assert m.chisel_releases_default_branch == "ubuntu-26.04"
    assert m.timeout_seconds == 600
    assert len(m.models) == 2
    assert m.models[0].effort == "low"   # default
    assert m.models[1].effort == "medium"  # override
    assert m.models[0].backend == "claude"


def test_load_manifest_scalar_model_id(tmp_path: Path) -> None:
    """Manifest accepts plain string in models list too."""
    raw = {
        "chisel_releases": {"url": "u", "sha": "HEAD", "branch": "ubuntu-26.04"},
        "models": ["claude-haiku-4-5-20251001"],
    }
    p = tmp_path / "manifest.yaml"
    p.write_text(yaml.safe_dump(raw), encoding="utf-8")
    m = load_manifest(p)
    assert m.models[0].id == "claude-haiku-4-5-20251001"


def test_discover_cases(tmp_path: Path) -> None:
    (tmp_path / "alpha").mkdir()
    (tmp_path / "alpha" / "case.yaml").write_text(
        "name: alpha\npackage: alpha\nbranch: ubuntu-26.04\n",
        encoding="utf-8",
    )
    (tmp_path / "beta").mkdir()
    (tmp_path / "beta" / "case.yaml").write_text(
        "name: beta\npackage: beta-pkg\nbranch: ubuntu-24.04\n",
        encoding="utf-8",
    )
    # dir w/out case.yaml is ignored
    (tmp_path / "gamma").mkdir()
    cases = discover_cases(tmp_path)
    names = [c.name for c in cases]
    assert names == ["alpha", "beta"]
    assert cases[1].package == "beta-pkg"
    assert cases[1].branch == "ubuntu-24.04"


def test_discover_cases_empty(tmp_path: Path) -> None:
    assert discover_cases(tmp_path) == ()
    assert discover_cases(tmp_path / "nonexistent") == ()
