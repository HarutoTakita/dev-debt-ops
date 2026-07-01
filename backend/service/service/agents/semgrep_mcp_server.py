"""In-house Semgrep MCP server (issue 069).

Exposes the project's Semgrep scan over the Model Context Protocol as an MCP tool over stdio. Wraps
the same engine the deterministic ``code_debt_detection`` pipeline uses (``services.semgrep_scan``).
NOTE (issue 275): the agent-first ``run_analysis_agent`` no longer attaches this MCP — Semgrep runs as
a deterministic program block in ``code_debt_detection``. Kept as a candidate for future agent wiring.

Why in-house rather than the official ``semgrep-mcp`` package: that package pins ``mcp==1.12.x``,
which conflicts with ``google-adk[mcp]`` (``mcp>=1.24``). A thin FastMCP server on our own
adk-compatible ``mcp`` avoids the conflict, needs no extra dependency or network, and runs fully
in-container. Launched as ``python -m service.agents.semgrep_mcp_server`` (stdio transport).
"""

import logging

from mcp.server.fastmcp import FastMCP

from service.services import semgrep_scan

logger = logging.getLogger(__name__)

mcp = FastMCP("semgrep")


@mcp.tool()
async def scan_code(files: list[dict]) -> list[dict]:
    """Run Semgrep static analysis over the given files and return code-debt findings.

    Pass the files you want analysed; each finding is aggregated per (file, type) where type is
    "security" (security/correctness) or "smell" (maintainability/best-practice). Use this to
    ground your judgement of which code carries real technical debt — the scan is deterministic.

    Args:
        files: List of ``{"filename": <repo-relative path>, "content": <file text>}`` objects.

    Returns:
        Findings as ``{"file_path", "type", "score", "notes", "metrics"}`` (empty if none / on error).
    """
    snapshot = {
        f["filename"]: f["content"]
        for f in files
        if isinstance(f, dict) and isinstance(f.get("filename"), str) and isinstance(f.get("content"), str)
    }
    aggregates = await semgrep_scan.scan_files(snapshot)
    return [
        {"file_path": a.file_path, "type": a.debt_type, "score": a.score, "notes": a.notes, "metrics": a.metrics}
        for a in aggregates
    ]


def main() -> None:
    """Run the Semgrep MCP server over stdio (entry point for ``python -m``)."""
    mcp.run()


if __name__ == "__main__":
    main()
