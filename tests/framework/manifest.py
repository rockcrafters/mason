from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

__all__ = ["Case", "Manifest", "Model", "discover_cases", "load_manifest"]


@dataclass(frozen=True)
class Model:
    id: str
    backend: str
    effort: str


@dataclass(frozen=True)
class Case:
    name: str
    package: str
    branch: str


@dataclass(frozen=True)
class Manifest:
    chisel_releases_url: str
    chisel_releases_sha: str
    chisel_releases_default_branch: str
    models: tuple[Model, ...]
    timeout_seconds: int
    stuck_timeout_seconds: int


def load_manifest(path: Path) -> Manifest:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    effort = raw.get("effort", "medium")
    backend = raw.get("backend", "claude")
    cr = raw["chisel_releases"]
    models = tuple(
        Model(
            id=m["id"] if isinstance(m, dict) else m,
            backend=(m.get("backend", backend) if isinstance(m, dict) else backend),
            effort=(m.get("effort", effort) if isinstance(m, dict) else effort),
        )
        for m in raw["models"]
    )
    return Manifest(
        chisel_releases_url=cr["url"],
        chisel_releases_sha=cr["sha"],
        chisel_releases_default_branch=cr["branch"],
        models=models,
        timeout_seconds=int(raw.get("timeout_seconds", 600)),
        stuck_timeout_seconds=int(raw.get("stuck_timeout_seconds", 300)),
    )


def discover_cases(cases_dir: Path) -> tuple[Case, ...]:
    """Walk tests/cases/<name>/case.yaml and load each."""
    out: list[Case] = []
    if not cases_dir.exists():
        return ()
    for child in sorted(cases_dir.iterdir()):
        if not child.is_dir():
            continue
        meta = child / "case.yaml"
        if not meta.exists():
            continue
        raw = yaml.safe_load(meta.read_text(encoding="utf-8"))
        out.append(
            Case(
                name=raw.get("name", child.name),
                package=raw["package"],
                branch=raw["branch"],
            )
        )
    return tuple(out)
