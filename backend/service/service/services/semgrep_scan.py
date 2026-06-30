"""Semgrep static-analysis integration for code-debt detection (issue 069).

Runs Semgrep (a fast, deterministic multi-language static analyser, 5,000+ rules) over a snapshot
of repository files and returns aggregated findings the ``code_debt_detection`` pipeline persists
into ``code_debts``. This adds *real* static-analysis signals (security / correctness / smells) on
top of the existing heuristics (complexity / duplication / dead code).

Design:
- Pure-ish: ``scan_files`` materialises the in-memory ``{path: content}`` snapshot to a temp dir and
  shells out to the bundled ``semgrep`` CLI (``semgrep scan --json``). No git clone needed.
- Deterministic + graceful: any failure (binary missing, timeout, non-JSON output) returns ``[]`` so
  detection still works with the heuristic detectors. Bounded by the caller's file cap + a timeout.
- Findings are aggregated **per (file, debt_type)** to fit the ``code_debts`` unique key
  ``(run_id, file_path, type)``; ``debt_type`` is ``security`` (security/correctness) or ``smell``
  (maintainability/best-practice/performance/other).

The same scan logic is exposed to the Twin Agent through the in-house Semgrep MCP server
(``service.agents.semgrep_mcp_server``), so the agent's judgement is grounded in the same engine.
"""

import asyncio
import json
import logging
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 120.0  # seconds; bounds a runaway scan
# Semgrep severity → code-debt score (0..1, higher = worse). quantize_severity maps these to bands.
_SEVERITY_SCORE = {"ERROR": 0.8, "WARNING": 0.5, "INFO": 0.3}
# Semgrep rule category (extra.metadata.category) → our code_debts `type`.
_SECURITY_CATEGORIES = frozenset({"security", "correctness"})


def _config() -> str:
    """Semgrep ruleset config (env ``SEMGREP_CONFIG``).

    Defaults to ``p/default`` — the registry's curated multi-language ruleset (free, no account,
    works with metrics disabled). Not ``auto``, which would require sending usage metrics.
    Override with a local ruleset path for fully offline / pinned scanning.
    """
    return os.environ.get("SEMGREP_CONFIG", "p/default")


@dataclass
class SemgrepAggregate:
    """Semgrep findings for one file, collapsed to a single code-debt row of one ``debt_type``."""

    file_path: str
    debt_type: str  # "security" | "smell"
    score: float
    notes: str
    metrics: dict = field(default_factory=dict)


def _category_to_type(category: str) -> str:
    """Map a Semgrep rule category to a ``code_debts`` type (security vs smell)."""
    return "security" if category.lower() in _SECURITY_CATEGORIES else "smell"


async def _semgrep_json(target_dir: str) -> dict | None:
    """Run ``semgrep scan --json`` over ``target_dir``; return parsed JSON or ``None`` on any failure.

    Isolated so tests can monkeypatch it without invoking the real binary.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "semgrep",
            "scan",
            "--json",
            "--quiet",
            "--metrics=off",
            "--config",
            _config(),
            ".",  # scan the cwd (the temp dir) so result paths are repo-relative, not absolute
            cwd=target_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except (FileNotFoundError, OSError):
        logger.warning("semgrep binary not available; skipping static analysis")
        return None
    try:
        async with asyncio.timeout(_DEFAULT_TIMEOUT):
            stdout, stderr = await proc.communicate()
    except TimeoutError:
        proc.kill()
        logger.warning("semgrep scan timed out after %ss; skipping static analysis", _DEFAULT_TIMEOUT)
        return None
    # Default exit codes: 0 (no findings) / 1 (findings) both emit JSON on stdout; >1 is an error.
    if proc.returncode is not None and proc.returncode > 1:
        logger.warning("semgrep scan failed (rc=%s): %s", proc.returncode, stderr.decode()[:500])
        return None
    try:
        return json.loads(stdout)
    except (json.JSONDecodeError, ValueError):
        logger.warning("semgrep produced no parseable JSON; skipping static analysis")
        return None


def _aggregate(results: list[dict]) -> list[SemgrepAggregate]:
    """Collapse raw Semgrep results into one aggregate per ``(file_path, debt_type)``."""
    buckets: dict[tuple[str, str], dict] = {}
    for r in results:
        path = r.get("path")
        if not isinstance(path, str) or not path:
            continue
        extra = r.get("extra") or {}
        severity = str(extra.get("severity") or "INFO").upper()
        category = str((extra.get("metadata") or {}).get("category") or "")
        debt_type = _category_to_type(category)
        rule_id = str(r.get("check_id") or "")
        line = (r.get("start") or {}).get("line")
        message = str(extra.get("message") or "").strip()

        key = (path, debt_type)
        b = buckets.setdefault(
            key,
            {"score": 0.0, "rule_ids": [], "lines": [], "messages": [], "max_severity": "INFO"},
        )
        b["score"] = max(b["score"], _SEVERITY_SCORE.get(severity, 0.3))
        if _SEVERITY_SCORE.get(severity, 0) >= _SEVERITY_SCORE.get(b["max_severity"], 0):
            b["max_severity"] = severity
        if rule_id and rule_id not in b["rule_ids"]:
            b["rule_ids"].append(rule_id)
        if isinstance(line, int):
            b["lines"].append(line)
        if message and message not in b["messages"]:
            b["messages"].append(message)

    aggregates: list[SemgrepAggregate] = []
    for (path, debt_type), b in buckets.items():
        count = len(b["lines"]) or len(b["rule_ids"])
        label = "セキュリティ" if debt_type == "security" else "コードスメル"
        top_msg = b["messages"][0] if b["messages"] else (b["rule_ids"][0] if b["rule_ids"] else "")
        notes = f"Semgrep（{label}）{count} 件" + (f": {top_msg}" if top_msg else "")
        aggregates.append(
            SemgrepAggregate(
                file_path=path,
                debt_type=debt_type,
                score=b["score"],
                notes=notes[:500],
                metrics={
                    "semgrep_count": count,
                    "max_severity": b["max_severity"],
                    "rule_ids": b["rule_ids"][:10],
                    "lines": sorted(set(b["lines"]))[:20],
                },
            )
        )
    return aggregates


async def scan_files(files: dict[str, str]) -> list[SemgrepAggregate]:
    """Scan a snapshot of files with Semgrep; return per-(file, type) aggregates (``[]`` on failure)."""
    if not files:
        return []
    try:
        with tempfile.TemporaryDirectory(prefix="semgrep-") as tmp:
            root = Path(tmp)
            for rel, content in files.items():
                dest = root / rel
                try:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_text(content, encoding="utf-8")
                except (OSError, ValueError):
                    continue  # skip a path we can't materialise; scan the rest
            data = await _semgrep_json(str(root))
    except OSError:
        # 一時ディレクトリの作成や I/O が環境要因で失敗（例: ディスク満杯 [Errno 28] No space left on device）。
        # Semgrep はベストエフォートなエンリッチで、ここで失敗してもヒューリスティックなコード負債検知は
        # 継続させねばならない（graceful）。docstring の「[] on failure」を温度差なく守る。
        logger.warning("semgrep scan skipped (filesystem error, e.g. ENOSPC)", exc_info=True)
        return []
    if not data:
        return []
    results = data.get("results")
    return _aggregate(results) if isinstance(results, list) else []
