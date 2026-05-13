"""sandbox setup: shallow-clone chisel-releases, copy skills/, prep targets.

Targets vary by kind:
- knockout: each target's slice exists in clone; snapshot as expected_yaml, then delete.
- denovo: each target's slice must NOT exist in clone; expected_yaml from <case_dir>/<pkg>.silver.yaml.
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from framework.manifest import Case

__all__ = [
    "Sandbox",
    "Target",
    "REPO_ROOT",
    "build_sandbox",
    "cr_clone_dir",
    "ensure_chisel_releases_clone",
]

REPO_ROOT = Path(__file__).resolve().parents[2]
TESTS_DIR = REPO_ROOT / "tests"
CACHE_DIR = TESTS_DIR / ".cache"
CR_CLONES_ROOT = CACHE_DIR / "chisel-releases"


def cr_clone_dir(branch: str) -> Path:
    """Per-branch clone dir. Cases on different branches stay isolated."""
    return CR_CLONES_ROOT / branch


@dataclass(frozen=True)
class Target:
    package: str
    slice_path: Path        # path inside sandbox where agent should write
    expected_yaml: str      # ground truth (golden for knockout, silver for denovo)


@dataclass(frozen=True)
class Sandbox:
    root: Path
    targets: tuple[Target, ...]
    kind: str

    @property
    def top(self) -> Target:
        return self.targets[0]

    # legacy single-target accessors -- top target only
    @property
    def slice_path(self) -> Path:
        return self.top.slice_path

    @property
    def expected_yaml(self) -> str:
        return self.top.expected_yaml

    @property
    def package(self) -> str:
        return self.top.package


def _run(cmd: list[str], cwd: Path | None = None) -> None:
    result = subprocess.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"command failed: {' '.join(cmd)}\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )


def ensure_chisel_releases_clone(url: str, branch: str, sha: str | None = None) -> Path:
    """Idempotent: per-branch clone dir; clone if missing, fetch + checkout pinned sha
    (else tip of branch)."""
    clone_dir = cr_clone_dir(branch)
    clone_dir.parent.mkdir(parents=True, exist_ok=True)
    if not clone_dir.exists():
        _run([
            "git", "clone",
            "--filter=blob:none",
            "--branch", branch,
            url,
            str(clone_dir),
        ])
    if sha and sha != "HEAD":
        _run(["git", "fetch", "--depth=1", "origin", sha], cwd=clone_dir)
        _run(["git", "checkout", sha], cwd=clone_dir)
    else:
        _run(["git", "fetch", "origin", branch], cwd=clone_dir)
        _run(["git", "checkout", f"origin/{branch}"], cwd=clone_dir)
    return clone_dir


def _short_hash(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]


def build_sandbox(
    case: Case,
    *,
    chisel_clone: Path,
    skills_src: Path,
    project_md_src: Path | None,
    workdir: Path,
) -> Sandbox:
    """Materialise sandbox dir at workdir. Returns Sandbox handle.

    - Clean workdir, copy chisel-releases working tree (no .git).
    - Per target in case.effective_targets:
        - knockout: snapshot slices/<pkg>.yaml -> expected_yaml; delete the file.
        - denovo: assert slices/<pkg>.yaml absent; load silver -> expected_yaml.
    - Copy skills/ + project CLAUDE.md so agent auto-loads the skill.
    """
    if workdir.exists():
        shutil.rmtree(workdir)
    workdir.mkdir(parents=True)

    for entry in chisel_clone.iterdir():
        if entry.name == ".git":
            continue
        dst = workdir / entry.name
        if entry.is_dir():
            shutil.copytree(entry, dst, symlinks=True)
        else:
            shutil.copy2(entry, dst)

    targets: list[Target] = []
    for pkg in case.effective_targets:
        slice_path = workdir / "slices" / f"{pkg}.yaml"
        if case.kind == "knockout":
            if not slice_path.exists():
                raise RuntimeError(
                    f"knockout target slice not found in clone: slices/{pkg}.yaml on {case.branch}"
                )
            expected_yaml = slice_path.read_text(encoding="utf-8")
            slice_path.unlink()
        else:  # denovo
            if slice_path.exists():
                raise RuntimeError(
                    f"denovo target slice already exists upstream -- silver is stale: "
                    f"slices/{pkg}.yaml on {case.branch}"
                )
            silver = case.silver_path(pkg)
            if silver is None or not silver.exists():
                raise RuntimeError(
                    f"denovo case missing silver for {pkg}: expected {silver}"
                )
            expected_yaml = silver.read_text(encoding="utf-8")
        targets.append(
            Target(package=pkg, slice_path=slice_path, expected_yaml=expected_yaml)
        )

    skills_dst = workdir / "skills"
    if skills_dst.exists():
        shutil.rmtree(skills_dst)
    shutil.copytree(skills_src, skills_dst, symlinks=False)

    if project_md_src is not None and project_md_src.exists():
        content = project_md_src.read_text(encoding="utf-8")
        (workdir / "CLAUDE.md").write_text(content, encoding="utf-8")

    return Sandbox(root=workdir, targets=tuple(targets), kind=case.kind)
