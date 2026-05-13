from __future__ import annotations

from dataclasses import dataclass, field
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
    package: str               # top-level pkg; drives /write-slice prompt
    branch: str
    sha: str | None = None
    kind: str = "knockout"     # "knockout" | "denovo"
    targets: tuple[str, ...] = ()   # all pkgs scored; () means (package,)
    case_dir: Path | None = None    # source dir for silver lookup (denovo)

    @property
    def effective_targets(self) -> tuple[str, ...]:
        return self.targets or (self.package,)

    def silver_path(self, pkg: str) -> Path | None:
        if self.case_dir is None:
            return None
        return self.case_dir / f"{pkg}.silver.yaml"


@dataclass(frozen=True)
class Manifest:
    chisel_releases_url: str
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
        kind = raw.get("kind", "knockout")
        if kind not in ("knockout", "denovo"):
            raise ValueError(f"{meta}: unknown kind {kind!r}")
        targets_raw = raw.get("targets") or []
        targets = tuple(targets_raw)
        out.append(
            Case(
                name=raw.get("name", child.name),
                package=raw["package"],
                branch=raw["branch"],
                sha=raw.get("sha"),
                kind=kind,
                targets=targets,
                case_dir=child,
            )
        )
    return tuple(out)
