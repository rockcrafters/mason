"""Tests for the scored pytest plugin via pytester."""
from __future__ import annotations

import json

import pytest

# inline plugin source path so pytester can register it
PLUGIN_IMPORT = "framework.scored_plugin"


def _make_project(pytester: pytest.Pytester) -> None:
    pytester.makeini(
        f"""
[pytest]
addopts = -p {PLUGIN_IMPORT}
""",
    )


def test_scored_returns_float(pytester: pytest.Pytester) -> None:
    _make_project(pytester)
    pytester.makepyfile(
        """
        import pytest

        @pytest.mark.scored
        def test_half() -> float:
            return 0.5
        """
    )
    result = pytester.runpytest("--scored-bar-width=4")
    result.assert_outcomes(passed=1)
    result.stdout.fnmatch_lines(["*test_half*0.50*"])


def test_scored_out_of_range_errors(pytester: pytest.Pytester) -> None:
    _make_project(pytester)
    pytester.makepyfile(
        """
        import pytest

        @pytest.mark.scored
        def test_too_big() -> float:
            return 1.5
        """
    )
    result = pytester.runpytest()
    # plugin raises UsageError -> exit code 4
    assert result.ret != 0


def test_scored_non_float_errors(pytester: pytest.Pytester) -> None:
    _make_project(pytester)
    pytester.makepyfile(
        """
        import pytest

        @pytest.mark.scored
        def test_str() -> str:
            return "nope"
        """
    )
    result = pytester.runpytest()
    assert result.ret != 0


def test_unscored_pass_records_as_one(pytester: pytest.Pytester) -> None:
    _make_project(pytester)
    pytester.makepyfile(
        """
        def test_plain():
            assert True
        """
    )
    result = pytester.runpytest()
    result.assert_outcomes(passed=1)
    result.stdout.fnmatch_lines(["*test_plain*1.00*"])


def test_json_report_shape(pytester: pytest.Pytester, tmp_path) -> None:
    _make_project(pytester)
    pytester.makepyfile(
        """
        import pytest

        @pytest.mark.scored
        def test_a() -> float: return 0.25

        @pytest.mark.scored
        def test_b() -> float: return 0.75
        """
    )
    report = tmp_path / "report.json"
    result = pytester.runpytest(f"--scored-report={report}")
    result.assert_outcomes(passed=2)
    assert report.exists()
    payload = json.loads(report.read_text())
    assert {t["id"].split("::")[-1] for t in payload["tests"]} == {"test_a", "test_b"}
    assert {t["score"] for t in payload["tests"]} == {0.25, 0.75}
    assert payload["overall"]["avg"] == pytest.approx(0.5)
    assert payload["overall"]["n"] == 2


def test_threshold_fails_when_below(pytester: pytest.Pytester) -> None:
    _make_project(pytester)
    pytester.makepyfile(
        """
        import pytest

        @pytest.mark.scored
        def test_low() -> float: return 0.1
        """
    )
    # scored-min above the score -> session exit non-zero
    result = pytester.runpytest("--scored-min=0.5")
    assert result.ret != 0


def test_parametrize_group_label_uses_name_attr(pytester: pytest.Pytester) -> None:
    """Plugin should label group axes by .name attr on dataclass-like params,
    not by repr."""
    _make_project(pytester)
    pytester.makepyfile(
        """
        from dataclasses import dataclass
        import pytest

        @dataclass(frozen=True)
        class Case:
            name: str

        @pytest.mark.scored
        @pytest.mark.parametrize("case", [Case(name="alpha"), Case(name="beta")])
        def test_x(case) -> float:
            return 1.0 if case.name == "alpha" else 0.5
        """
    )
    result = pytester.runpytest()
    result.assert_outcomes(passed=2)
    # group rendering should show case=alpha, case=beta (not Case(name=...))
    result.stdout.fnmatch_lines(["*alpha*1.00*"])
    result.stdout.fnmatch_lines(["*beta*0.50*"])
