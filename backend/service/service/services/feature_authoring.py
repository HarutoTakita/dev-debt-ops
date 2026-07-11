"""Agentic feature-clustering orchestration (issue 263).

Drives the feature-clustering agent via ``run_single_agent`` (trace + secret-redaction plugins) and
falls back to ``gemini_stack_service.cluster_features`` on any failure / empty result — so the
pipeline always receives the feature list. One model call; no repo clone / MCP.
"""

import logging
from typing import Any

from service.agents.budget import RunBudget
from service.agents.feature_agent import build_feature_agent
from service.agents.single_agent import run_single_agent
from service.services import gemini_stack_service

logger = logging.getLogger(__name__)


def _files_block(paths: list[str], descriptors: dict[str, str] | None) -> str:
    """One line per file: ``path`` or ``path — purpose`` when a descriptor is known (semantic signal)."""
    desc = descriptors or {}
    return "\n".join(f"{p} — {desc[p]}" if desc.get(p) else p for p in paths)


async def cluster_features_agentic(
    paths: list[str],
    edges: list[tuple[str, str]],
    *,
    owner: str,
    repo: str,
    descriptors: dict[str, str] | None = None,
) -> list[dict]:
    """Cluster files into features via an ADK agent, falling back to the direct Gemini path.

    The agent receives the file list (annotated with each file's *purpose* when known, so it clusters by
    what code does — not filename alone) + import edges and calls ``save_features``; on any failure or an
    empty result we fall back to ``gemini_stack_service.cluster_features`` so behaviour never regresses.
    """
    if not paths:
        return []
    captured: dict[str, Any] = {}
    files_block = _files_block(paths, descriptors)
    edges_block = "\n".join(f"{a} -> {b}" for a, b in edges) or "(none)"
    prompt = f"=== files (path — purpose) ===\n{files_block}\n\n=== import edges (from -> to) ===\n{edges_block}"
    try:
        agent = build_feature_agent(budget=RunBudget(), captured=captured)
        await run_single_agent(
            agent=agent,
            prompt=prompt,
            user_id=f"{owner}_{repo}",
            redaction_allowlist=[owner, repo, f"{owner}/{repo}"],
        )
    except Exception as exc:  # any agent/runtime failure → fall back to the direct path
        logger.warning("feature-clustering(agentic) failed for %s/%s: %s; falling back to direct", owner, repo, exc)

    features = captured.get("features") or []
    if features:
        return features
    return await gemini_stack_service.cluster_features(paths, edges, descriptors=descriptors)
