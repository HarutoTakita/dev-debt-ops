"""Trivy security-scan integration (issue 278): JSON aggregation + graceful failure.

The real ``trivy`` binary is never invoked — ``_trivy_json`` is monkeypatched, mirroring
``test_semgrep_scan``. Aggregation to per-file ``security`` rows is exercised directly.
"""

import pytest

from service.services import trivy_scan

_TRIVY_JSON = {
    "Results": [
        {
            "Target": "requirements.txt",
            "Class": "lang-pkgs",
            "Vulnerabilities": [
                {"VulnerabilityID": "CVE-2024-1", "Severity": "HIGH", "Title": "requests vuln"},
                {"VulnerabilityID": "CVE-2024-2", "Severity": "CRITICAL", "Title": "urllib3 vuln"},
            ],
        },
        {
            "Target": "src/app.py",
            "Class": "secret",
            "Secrets": [{"RuleID": "aws-key", "Severity": "CRITICAL", "Title": "AWS secret"}],
        },
        {"Target": "clean.py", "Class": "lang-pkgs"},  # no findings → not aggregated
    ]
}


class TestAggregate:
    def test_aggregates_per_file_as_security(self) -> None:
        aggs = {a.file_path: a for a in trivy_scan._aggregate(_TRIVY_JSON["Results"])}
        assert set(aggs) == {"requirements.txt", "src/app.py"}  # clean.py dropped
        req = aggs["requirements.txt"]
        assert req.debt_type == "security"
        assert req.score == trivy_scan._SEVERITY_SCORE["CRITICAL"]  # worst severity wins
        assert req.metrics["trivy_vuln"] == 2
        assert req.metrics["max_severity"] == "CRITICAL"
        assert "Trivy" in req.notes
        assert aggs["src/app.py"].metrics["trivy_secret"] == 1


class TestScanRepo:
    async def test_empty_repo_dir_is_noop(self) -> None:
        assert await trivy_scan.scan_repo("") == []

    async def test_graceful_when_binary_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def _none(_dir: str) -> dict | None:
            return None  # simulates trivy missing / timeout / bad JSON

        monkeypatch.setattr(trivy_scan, "_trivy_json", _none)
        assert await trivy_scan.scan_repo("/tmp/x") == []

    async def test_scan_repo_aggregates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def _fake(_dir: str) -> dict:
            return _TRIVY_JSON

        monkeypatch.setattr(trivy_scan, "_trivy_json", _fake)
        out = await trivy_scan.scan_repo("/tmp/x")
        assert {a.file_path for a in out} == {"requirements.txt", "src/app.py"}
        assert all(a.debt_type == "security" for a in out)
