"""Agentic repayment-refactor proposal orchestration (issue 217 PR3).

Clones the repo so Serena (LSP) can check callers / references, drives the refactor agent via
``run_single_agent`` (trace + secret-redaction plugins), applies the same plausibility guard as the
direct path, and falls back to ``gemini_stack_service.generate_refactor`` on any failure / empty /
implausible output — so the PR write in the pipeline always receives a safe ``{new_content,
pr_title, pr_body}``.
"""

import logging
from typing import Any

from service.agents.budget import RunBudget
from service.agents.refactor_agent import build_refactor_agent
from service.agents.serena_mcp import build_serena_toolset
from service.agents.single_agent import run_single_agent
from service.services import gemini_stack_service, repo_checkout

logger = logging.getLogger(__name__)


async def _run_refactor_agent(
    owner: str, repo: str, ref: str, path: str, content: str, notes: str, token: str
) -> dict[str, Any]:
    """Drive the refactor agent over one file; return the proposal it saved (``{}`` if none)."""
    repo_dir = await repo_checkout.shallow_clone(owner, repo, ref, token)
    serena = build_serena_toolset(repo_dir) if repo_dir else None
    captured: dict[str, Any] = {}
    agent = build_refactor_agent(
        path=path,
        notes=notes,
        budget=RunBudget(),
        captured=captured,
        serena_toolset=serena,
    )
    prompt = f"対象ファイル「{path}」の現在の全文:\n\n{content}"
    try:
        await run_single_agent(
            agent=agent,
            prompt=prompt,
            user_id=f"{owner}_{repo}",
            toolsets=[serena] if serena else None,
        )
    finally:
        if repo_dir:
            repo_checkout._cleanup(repo_dir)
    return captured


async def generate_refactor_agentic(
    owner: str, repo: str, ref: str, path: str, content: str, notes: str, *, token: str
) -> dict[str, str]:
    """Agentic refactor proposal with fallback to the direct path (issue 217 PR3).

    The agent reads the file and follows callers / references via Serena, then saves a proposal. The
    proposed content is accepted only if it passes the plausibility guard (bounded, non-empty edit);
    otherwise — and on any agent failure or empty result — this falls back to the direct Gemini
    refactor, so behaviour never regresses below the non-agentic path.
    """
    captured: dict[str, Any] = {}
    try:
        captured = await _run_refactor_agent(owner, repo, ref, path, content, notes, token)
    except Exception as exc:  # any agent/runtime failure → fall back to the direct path
        logger.warning("repayment-refactor(agentic) failed for %s: %s; falling back to direct", path, exc)

    proposed = str(captured.get("new_content") or "")
    if proposed and gemini_stack_service._is_plausible_refactor(content, proposed):
        return {
            "new_content": proposed,
            "pr_title": str(captured.get("pr_title") or f"Repay code debt in {path}"),
            "pr_body": str(captured.get("pr_body") or "Automated repayment refactor."),
        }
    return await gemini_stack_service.generate_refactor(path, content, notes)
