"""Agentic quiz authoring orchestration (issue 217 PR3).

Clones the repo so Serena (LSP) can follow dependencies / references, drives the quiz agent via
``run_single_agent`` (trace + secret-redaction plugins), and falls back to
``gemini_stack_service.generate_quiz`` on any failure / empty result — so the pipeline always
receives ``{questions, answer_key}``.
"""

import logging
from typing import Any

from service.agents.budget import RunBudget
from service.agents.quiz_agent import build_quiz_agent
from service.agents.serena_mcp import build_serena_toolset
from service.agents.single_agent import run_single_agent
from service.services import gemini_stack_service, repo_checkout

logger = logging.getLogger(__name__)


async def _run_quiz_agent(owner: str, repo: str, ref: str, label: str, content: str, token: str) -> dict[str, Any]:
    """Drive the quiz agent over one target; return the quiz it saved (``{}`` if none)."""
    repo_dir = await repo_checkout.shallow_clone(owner, repo, ref, token)
    serena = build_serena_toolset(repo_dir) if repo_dir else None
    captured: dict[str, Any] = {}
    agent = build_quiz_agent(label=label, budget=RunBudget(), captured=captured, serena_toolset=serena)
    prompt = f"対象「{label}」のコード:\n\n{content}"
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


async def generate_quiz_agentic(owner: str, repo: str, ref: str, label: str, content: str, *, token: str) -> dict:
    """Agentic quiz authoring with fallback to the direct path (issue 217 PR3).

    The agent reads the code and follows dependencies via Serena, then saves the quiz. On any failure
    or an empty result it falls back to the direct Gemini quiz generation, so behaviour never
    regresses below the non-agentic path.
    """
    captured: dict[str, Any] = {}
    try:
        captured = await _run_quiz_agent(owner, repo, ref, label, content, token)
    except Exception as exc:  # any agent/runtime failure → fall back to the direct path
        logger.warning("quiz-authoring(agentic) failed for %s: %s; falling back to direct", label, exc)

    questions = captured.get("questions") or []
    if questions:
        return {"questions": questions, "answer_key": captured.get("answer_key") or {}}
    return await gemini_stack_service.generate_quiz(label, content)
