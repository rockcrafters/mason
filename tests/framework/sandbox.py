"""sandbox setup: shallow-clone chisel-releases, copy skills/, nuke target slice."""
from __future__ import annotations

import hashlib
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

__all__ = ["Sandbox", "REPO_ROOT", "build_sandbox", "ensure_chisel_releases_clone"]

REPO_ROOT = Path(__file__).resolve().parents[2]
TESTS_DIR = REPO_ROOT / "tests"
CACHE_DIR = TESTS_DIR / ".cache"
CR_CLONE_DIR = CACHE_DIR / "chisel-releases"


@dataclass(frozen=True)
class Sandbox:
    root: Path                # agent's cwd
    slice_path: Path          # path inside root where target slice lives
    expected_yaml: str        # original yaml content (ground truth)
    package: str


def _run(cmd: list[str], cwd: Path | None = None) -> None:
    result = subprocess.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"command failed: {' '.join(cmd)}\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )


def ensure_chisel_releases_clone(url: str, branch: str, sha: str) -> Path:
    """Idempotent: clone if missing, fetch + checkout pinned sha."""
    CR_CLONE_DIR.parent.mkdir(parents=True, exist_ok=True)
    if not CR_CLONE_DIR.exists():
        _run([
            "git", "clone",
            "--filter=blob:none",
            "--branch", branch,
            url,
            str(CR_CLONE_DIR),
        ])
    if sha and sha != "HEAD":
        _run(["git", "fetch", "--depth=1", "origin", sha], cwd=CR_CLONE_DIR)
        _run(["git", "checkout", sha], cwd=CR_CLONE_DIR)
    else:
        _run(["git", "fetch", "origin", branch], cwd=CR_CLONE_DIR)
        _run(["git", "checkout", f"origin/{branch}"], cwd=CR_CLONE_DIR)
    return CR_CLONE_DIR


def _short_hash(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]


def build_sandbox(
    package: str,
    branch: str,
    *,
    chisel_clone: Path,
    skills_src: Path,
    project_md_src: Path | None,
    workdir: Path,
) -> Sandbox:
    """Materialise sandbox dir at workdir. Returns Sandbox handle.

    - Clean workdir.
    - Copy chisel-releases checkout (already on correct branch/sha) into workdir.
    - Read original slices/<pkg>.yaml as expected_yaml.
    - Delete that file in sandbox.
    - Copy skills/ + CLAUDE.md so agent loads the slice skill.
    """
    if workdir.exists():
        shutil.rmtree(workdir)
    workdir.mkdir(parents=True)

    # copy chisel-releases working tree (exclude .git for speed)
    for entry in chisel_clone.iterdir():
        if entry.name == ".git":
            continue
        dst = workdir / entry.name
        if entry.is_dir():
            shutil.copytree(entry, dst, symlinks=True)
        else:
            shutil.copy2(entry, dst)

    slice_path = workdir / "slices" / f"{package}.yaml"
    if not slice_path.exists():
        raise RuntimeError(
            f"target slice not found in clone: slices/{package}.yaml on {branch}"
        )
    expected_yaml = slice_path.read_text(encoding="utf-8")
    slice_path.unlink()

    # copy skills/
    skills_dst = workdir / "skills"
    if skills_dst.exists():
        shutil.rmtree(skills_dst)
    shutil.copytree(skills_src, skills_dst, symlinks=False)

    # copy project CLAUDE.md (or AGENTS.md target) so agent auto-loads skill
    if project_md_src is not None and project_md_src.exists():
        # resolve symlink + write as real file at CLAUDE.md
        content = project_md_src.read_text(encoding="utf-8")
        (workdir / "CLAUDE.md").write_text(content, encoding="utf-8")

    return Sandbox(
        root=workdir,
        slice_path=slice_path,
        expected_yaml=expected_yaml,
        package=package,
    )
