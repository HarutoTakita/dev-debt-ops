"""Agentic tech-stack orchestration (issue 263).

Drives the tech-stack agent via ``run_single_agent`` (trace + secret-redaction) and falls back to
``gemini_stack_service.analyze_tech_stack`` on any failure / empty result — so the pipeline always
receives a classification dict. One model call; no repo clone / MCP.
"""

import logging
from typing import Any

from service.agents.budget import RunBudget
from service.agents.single_agent import run_single_agent
from service.agents.stack_agent import build_stack_agent
from service.services import gemini_stack_service

logger = logging.getLogger(__name__)


async def classify_stack_agentic(files: dict[str, str], *, owner: str, repo: str) -> dict:
    """Classify the tech stack via an ADK agent, falling back to the direct Gemini path.

    The agent reads the key files and calls ``save_stack``; on any failure or an empty result we
    fall back to ``gemini_stack_service.analyze_tech_stack`` so behaviour never regresses.
    """
    if not files:
        return await gemini_stack_service.analyze_tech_stack(files)  # returns the empty-result shape
    captured: dict[str, Any] = {}
    prompt = gemini_stack_service._build_file_section(files)
    try:
        agent = build_stack_agent(budget=RunBudget(), captured=captured)
        await run_single_agent(
            agent=agent,
            prompt=prompt,
            user_id=f"{owner}_{repo}",
            redaction_allowlist=[owner, repo, f"{owner}/{repo}"],
        )
    except Exception as exc:  # any agent/runtime failure → fall back to the direct path
        logger.warning("tech-stack(agentic) failed for %s/%s: %s; falling back to direct", owner, repo, exc)

    stack = captured.get("stack")
    if isinstance(stack, dict) and stack.get("languages"):
        return stack
    return await gemini_stack_service.analyze_tech_stack(files)
