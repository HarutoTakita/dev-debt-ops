"""issue 069: Semgrep static-analysis integration — JSON→aggregate mapping + graceful fallback.

The real semgrep binary is exercised in e2e; here we verify the pure aggregation (category→type,
severity→score, per-(file,type) collapse) and that any scan failure degrades to ``[]`` so
``code_debt_detection`` keeps working on heuristics alone.
"""

import pytest

from service.services import semgrep_scan


def test_category_to_type() -> None:
    assert semgrep_scan._category_to_type("security") == "security"
    assert semgrep_scan._category_to_type("correctness") == "security"
    assert semgrep_scan._category_to_type("maintainability") == "smell"
    assert semgrep_scan._category_to_type("") == "smell"


def test_aggregate_collapses_per_file_and_type() -> None:
    results = [
        {
            "path": "app/run.py",
            "check_id": "py.subprocess-shell-true",
            "start": {"line": 3},
            "extra": {"severity": "ERROR", "message": "shell=True is dangerous", "metadata": {"category": "security"}},
        },
        {
            "path": "app/run.py",
            "check_id": "py.another-security",
            "start": {"line": 9},
            "extra": {"severity": "WARNING", "message": "weak hash", "metadata": {"category": "security"}},
        },
        {
            "path": "app/run.py",
            "check_id": "py.style",
            "start": {"line": 1},
            "extra": {"severity": "INFO", "message": "style nit", "metadata": {"category": "maintainability"}},
        },
    ]
    aggs = {(a.file_path, a.debt_type): a for a in semgrep_scan._aggregate(results)}
    # security (2 findings, max ERROR) + smell (1 finding) → two rows for the one file
    assert set(aggs) == {("app/run.py", "security"), ("app/run.py", "smell")}
    sec = aggs[("app/run.py", "security")]
    assert sec.score == semgrep_scan._SEVERITY_SCORE["ERROR"]
    assert sec.metrics["semgrep_count"] == 2
    assert sec.metrics["max_severity"] == "ERROR"
    assert sec.metrics["lines"] == [3, 9]
    assert len(sec.metrics["rule_ids"]) == 2


def test_aggregate_skips_pathless_results() -> None:
    assert semgrep_scan._aggregate([{"extra": {"severity": "ERROR"}}]) == []


async def test_scan_files_empty_input() -> None:
    assert await semgrep_scan.scan_files({}) == []


async def test_scan_files_degrades_on_filesystem_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A disk-full / temp-dir failure (ENOSPC) must NOT crash code-debt detection — return [] (issue 254)."""

    def _enospc(*_args: object, **_kwargs: object):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(semgrep_scan.tempfile, "TemporaryDirectory", _enospc)
    assert await semgrep_scan.scan_files({"a.py": "x = 1\n"}) == []


async def test_scan_files_degrades_when_semgrep_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _no_json(_target_dir: str) -> dict | None:
        return None  # simulates missing binary / timeout / bad output

    monkeypatch.setattr(semgrep_scan, "_semgrep_json", _no_json)
    assert await semgrep_scan.scan_files({"a.py": "x = 1\n"}) == []


async def test_scan_files_maps_results(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_json(_target_dir: str) -> dict:
        return {
            "results": [
                {
                    "path": "a.py",
                    "check_id": "r1",
                    "start": {"line": 2},
                    "extra": {"severity": "ERROR", "message": "bad", "metadata": {"category": "security"}},
                }
            ]
        }

    monkeypatch.setattr(semgrep_scan, "_semgrep_json", _fake_json)
    aggs = await semgrep_scan.scan_files({"a.py": "import os\n"})
    assert len(aggs) == 1
    assert aggs[0].file_path == "a.py"
    assert aggs[0].debt_type == "security"
