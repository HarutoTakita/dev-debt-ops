"""Trivy security-scan integration for code-debt detection (issue 278).

Runs Trivy (SCA / secret / misconfiguration scanner) over a checked-out repository and returns
aggregated findings the ``code_debt_detection`` pipeline persists into ``code_debts``. This restores
the SCA/secret/misconfig signal axis that used to reach the analysis only through the (now removed)
Twin Agent's Trivy MCP — as a *deterministic program block* instead of an agent tool.

Design (mirrors ``semgrep_scan``):
- Deterministic + graceful: any failure (binary missing, timeout, non-JSON) returns ``[]`` so
  detection still works without Trivy. Bounded by a timeout.
- Needs a real checked-out tree (``repo_dir``) — unlike Semgrep's in-memory snapshot — because
  Trivy's value (vulnerable dependencies, secrets, IaC misconfig) lives in lockfiles / manifests /
  config files, not just the filtered source set. The agentic pipeline reuses the shallow clone it
  already makes for the Base Analysis Agent, so no extra clone is needed.
- Findings are aggregated **per file** into a single ``security`` code-debt row (the frontend's
  ``code_debts.type`` enum has no vuln/secret/misconfig members; Trivy is a security scanner, so
  ``security`` is the honest bucket). Score scales with the worst severity on that file.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 180.0  # seconds; bounds a runaway scan (vuln DB lookups can be slow)
# Trivy severity → code-debt score (0..1, higher = worse). quantize_severity maps these to bands.
_SEVERITY_SCORE = {"CRITICAL": 0.9, "HIGH": 0.7, "MEDIUM": 0.5, "LOW": 0.3, "UNKNOWN": 0.3}
_SEVERITY_RANK = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "UNKNOWN": 0}


@dataclass
class TrivyAggregate:
    """Trivy findings for one file, collapsed to a single ``security`` code-debt row."""

    file_path: str
    debt_type: str  # always "security" (Trivy is a security scanner; fits the code_debts enum)
    score: float
    notes: str
    metrics: dict = field(default_factory=dict)


async def _trivy_json(target_dir: str) -> dict | None:
    """Run ``trivy fs --format json`` over ``target_dir``; return parsed JSON or ``None`` on failure.

    Isolated so tests can monkeypatch it without invoking the real binary.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "trivy",
            "fs",
            "--scanners",
            "vuln,secret,misconfig",
            "--format",
            "json",
            "--quiet",
            "--no-progress",
            ".",  # scan the cwd so result Targets are repo-relative, not absolute
            cwd=target_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except (FileNotFoundError, OSError):
        logger.warning("trivy binary not available; skipping security scan")
        return None
    try:
        async with asyncio.timeout(_DEFAULT_TIMEOUT):
            stdout, stderr = await proc.communicate()
    except TimeoutError:
        proc.kill()
        logger.warning("trivy scan timed out after %ss; skipping security scan", _DEFAULT_TIMEOUT)
        return None
    if proc.returncode not in (0, None):
        logger.warning("trivy scan failed (rc=%s): %s", proc.returncode, stderr.decode()[:500])
        return None
    try:
        return json.loads(stdout)
    except (json.JSONDecodeError, ValueError):
        logger.warning("trivy produced no parseable JSON; skipping security scan")
        return None


def _aggregate(results: list[dict]) -> list[TrivyAggregate]:
    """Collapse raw Trivy results into one ``security`` aggregate per file (Target)."""
    buckets: dict[str, dict] = {}
    for r in results:
        target = r.get("Target")
        if not isinstance(target, str) or not target:
            continue
        # (category, list-key, id-key, per-file counter) for the three scanners.
        specs = (
            ("vuln", "Vulnerabilities", "VulnerabilityID"),
            ("secret", "Secrets", "RuleID"),
            ("misconfig", "Misconfigurations", "ID"),
        )
        for category, list_key, id_key in specs:
            items = r.get(list_key)
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                severity = str(item.get("Severity") or "UNKNOWN").upper()
                title = str(item.get("Title") or item.get(id_key) or "").strip()
                b = buckets.setdefault(
                    target,
                    {"score": 0.0, "max_severity": "UNKNOWN", "counts": {}, "titles": []},
                )
                b["score"] = max(b["score"], _SEVERITY_SCORE.get(severity, 0.3))
                if _SEVERITY_RANK.get(severity, 0) >= _SEVERITY_RANK.get(b["max_severity"], 0):
                    b["max_severity"] = severity
                b["counts"][category] = b["counts"].get(category, 0) + 1
                if title and title not in b["titles"]:
                    b["titles"].append(title)

    _LABELS = {"vuln": "脆弱性", "secret": "secret", "misconfig": "設定ミス"}
    aggregates: list[TrivyAggregate] = []
    for target, b in buckets.items():
        parts = [f"{_LABELS[c]} {n} 件" for c, n in b["counts"].items() if n]
        top = b["titles"][0] if b["titles"] else ""
        notes = "Trivy（" + " / ".join(parts) + "）" + (f": {top}" if top else "")
        aggregates.append(
            TrivyAggregate(
                file_path=target,
                debt_type="security",
                score=b["score"],
                notes=notes[:500],
                metrics={
                    "max_severity": b["max_severity"],
                    **{f"trivy_{c}": n for c, n in b["counts"].items()},
                },
            )
        )
    return aggregates


async def scan_repo(repo_dir: str) -> list[TrivyAggregate]:
    """Scan a checked-out repository with Trivy; return per-file ``security`` aggregates (``[]`` on failure)."""
    if not repo_dir:
        return []
    data = await _trivy_json(repo_dir)
    if not data:
        return []
    results = data.get("Results")
    return _aggregate(results) if isinstance(results, list) else []
