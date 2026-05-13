"""Fixtures + scored plugin registration for slice-skill tests.

Scoped to tests/slice/ -- meta tests don't pick this up, so they run
as plain pytest (no scored bar table, no parametrize injection).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

# register scored plugin -- assertion rewriting enabled before import
pytest.register_assert_rewrite("framework.scored_plugin")
pytest_plugins = ["framework.scored_plugin"]

from framework.manifest import Case, Manifest, Model, discover_cases, load_manifest

TESTS_DIR = Path(__file__).resolve().parent.parent
MANIFEST_PATH = TESTS_DIR / "manifest.yaml"
CASES_DIR = TESTS_DIR / "cases"
RUNS_DIR = TESTS_DIR / ".cache" / "runs"


@dataclass(frozen=True)
class Run:
    case: Case
    model: Model
    run_dir: Path

    @property
    def result_path(self) -> Path:
        return self.run_dir / f"{self.case.package}.yaml"

    @property
    def expected_path(self) -> Path:
        return self.run_dir / f"{self.case.package}.expected.yaml"

    @property
    def metadata(self) -> dict:
        p = self.run_dir / "metadata.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

    @property
    def expected_yaml(self) -> str:
        return (
            self.expected_path.read_text(encoding="utf-8")
            if self.expected_path.exists()
            else ""
        )

    @property
    def slice_path(self) -> Path:
        return self.result_path


def _discover_runs() -> list[Run]:
    if not RUNS_DIR.exists():
        return []
    manifest = load_manifest(MANIFEST_PATH)
    cases_by_name = {c.name: c for c in discover_cases(CASES_DIR)}
    models_by_id = {m.id: m for m in manifest.models}
    out: list[Run] = []
    for model_dir in sorted(RUNS_DIR.iterdir()):
        if not model_dir.is_dir():
            continue
        model = models_by_id.get(model_dir.name)
        if model is None:
            continue
        for case_dir in sorted(model_dir.iterdir()):
            if not case_dir.is_dir():
                continue
            case = cases_by_name.get(case_dir.name)
            if case is None:
                continue
            out.append(Run(case=case, model=model, run_dir=case_dir))
    return out


@pytest.fixture(scope="session")
def manifest() -> Manifest:
    return load_manifest(MANIFEST_PATH)


@pytest.fixture
def run(request) -> Run:
    return request.param


@pytest.fixture
def agent_output(run: Run) -> Run:
    if not run.result_path.exists():
        pytest.skip(f"no result.yaml for {run.case.name}/{run.model.id} -- run `make run`")
    return run


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Parametrize over discovered (case, model) runs in .cache/runs/."""
    if "run" not in metafunc.fixturenames:
        return
    runs = _discover_runs()
    if not runs:
        metafunc.parametrize(
            "run",
            [
                pytest.param(
                    None,
                    marks=pytest.mark.skip(
                        reason="no runs in .cache/runs/ -- run `make run`"
                    ),
                )
            ],
            ids=["no-runs"],
        )
        return
    metafunc.parametrize(
        "run",
        runs,
        ids=[f"{r.case.name}-{r.model.id}" for r in runs],
        indirect=True,
    )
