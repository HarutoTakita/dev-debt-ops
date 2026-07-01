"""Agentic learning-plan orchestration (issue 263).

Drives the learning-steps / external-resources agents via ``run_single_agent`` (trace + secret
redaction) and falls back to the direct ``gemini_stack_service`` calls on any failure / empty result
— so the learning-plan pipeline always receives its steps / resources. One model call each.
"""

import logging
from typing import Any

from service.agents.budget import RunBudget
from service.agents.learning_agent import build_external_resources_agent, build_learning_steps_agent
from service.agents.single_agent import run_single_agent
from service.services import gemini_stack_service

logger = logging.getLogger(__name__)


async def generate_code_learning_steps_agentic(
    feature_name: str, feature_description: str, file_paths: list[str], *, owner: str, repo: str
) -> list[dict]:
    """Generate code-learning steps via an ADK agent, falling back to the direct Gemini path."""
    if not file_paths:
        return []
    captured: dict[str, Any] = {}
    files_block = "\n".join(f"- {p}" for p in file_paths)
    prompt = f"機能名: {feature_name}\n説明: {feature_description or '（説明なし）'}\n構成ファイル:\n{files_block}"
    try:
        agent = build_learning_steps_agent(budget=RunBudget(), captured=captured)
        await run_single_agent(
            agent=agent, prompt=prompt, user_id=f"{owner}_{repo}", redaction_allowlist=[owner, repo, f"{owner}/{repo}"]
        )
    except Exception as exc:
        logger.warning("learning-steps(agentic) failed for %s/%s: %s; falling back to direct", owner, repo, exc)
    steps = captured.get("steps") or []
    if steps:
        return steps
    return await gemini_stack_service.generate_code_learning_steps(feature_name, feature_description, file_paths)


async def generate_external_resources_agentic(gap_concepts: list[str], *, owner: str, repo: str) -> list[dict]:
    """Generate external learning resources via an ADK agent, falling back to the direct Gemini path."""
    if not gap_concepts:
        return []
    captured: dict[str, Any] = {}
    prompt = "ギャップ概念/技術用語:\n" + "\n".join(f"- {c}" for c in gap_concepts)
    try:
        agent = build_external_resources_agent(budget=RunBudget(), captured=captured)
        await run_single_agent(
            agent=agent, prompt=prompt, user_id=f"{owner}_{repo}", redaction_allowlist=[owner, repo, f"{owner}/{repo}"]
        )
    except Exception as exc:
        logger.warning("external-resources(agentic) failed for %s/%s: %s; falling back to direct", owner, repo, exc)
    resources = captured.get("resources") or []
    if resources:
        return resources
    return await gemini_stack_service.generate_external_resources(gap_concepts)
