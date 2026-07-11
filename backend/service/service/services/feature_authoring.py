"""Agentic feature-clustering orchestration (issue 263).

Drives the feature-clustering agent via ``run_single_agent`` (trace + secret-redaction plugins) and
falls back to ``gemini_stack_service.cluster_features`` on any failure / empty result — so the
pipeline always receives the feature list. One model call; no repo clone / MCP.
"""

import asyncio
import logging
from collections import defaultdict
from typing import Any

from service.agents.budget import RunBudget
from service.agents.feature_agent import build_feature_agent
from service.agents.single_agent import run_single_agent
from service.services import gemini_stack_service

logger = logging.getLogger(__name__)

_ASSIGN_BATCH = 30  # files per assignment LLM call — small enough to stay accurate + avoid output truncation
_ASSIGN_CONCURRENCY = 4  # concurrent assignment calls (Gemini retries handle rate limits)
_ASSIGN_CONFIDENCE = 0.8  # confidence for LLM batch-assigned files (vs the single-shot 1.0)


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


async def cluster_features_capability_first(
    paths: list[str],
    edges: list[tuple[str, str]],
    *,
    owner: str,
    repo: str,
    descriptors: dict[str, str] | None = None,
) -> list[dict]:
    """Two-phase clustering: LLM enumerates capabilities, then assigns files to them in batches.

    Fixes the single-shot failure mode where the model won't emit assignments for all ~400 files
    (coverage ≈ 6%). (1) ``propose_capabilities`` lists capability names only — small output, so many
    are produced reliably. (2) files are split into ``_ASSIGN_BATCH`` chunks and each is assigned to the
    fixed capability list via ``assign_files_to_capabilities`` (multi-membership, run concurrently).
    Assignment stays an LLM judgment (more accurate than deterministic path matching). If the capability
    proposal is empty/failing, falls back to the single-shot ``cluster_features_agentic`` (no regression).
    Returns the pipeline's standard shape ``[{key, name, description, files: [{path, confidence}]}]``.
    """
    if not paths:
        return []
    desc = descriptors or {}
    fwp = [(p, desc.get(p, "")) for p in paths]
    try:
        caps = await gemini_stack_service.propose_capabilities(fwp)
    except Exception as exc:
        logger.warning("capability proposal failed for %s/%s: %s; falling back to single-shot", owner, repo, exc)
        caps = []
    caps = [c for c in caps if isinstance(c, dict) and c.get("key")]
    if not caps:
        return await cluster_features_agentic(paths, edges, owner=owner, repo=repo, descriptors=descriptors)

    # assign が返す識別子が key 完全一致でなくても（name を返す・大小/記号違い等）canonical key に解決する。
    # これを怠ると 1 件も一致せず全機能が空になり得る（実測: capability-first で 0 機能に退行した原因）。
    def _norm(s: str) -> str:
        return "".join(ch for ch in str(s).lower() if ch.isalnum())

    resolve: dict[str, str] = {}
    for c in caps:
        k = str(c["key"])
        resolve[_norm(k)] = k
        if c.get("name"):
            resolve.setdefault(_norm(c["name"]), k)

    batches = [fwp[i : i + _ASSIGN_BATCH] for i in range(0, len(fwp), _ASSIGN_BATCH)]
    sem = asyncio.Semaphore(_ASSIGN_CONCURRENCY)

    async def _assign(batch: list[tuple[str, str]]) -> dict[str, list[str]]:
        async with sem:
            try:
                return await gemini_stack_service.assign_files_to_capabilities(caps, batch)
            except Exception:
                logger.exception("file-assignment batch failed for %s/%s", owner, repo)
                return {}

    results = await asyncio.gather(*(_assign(b) for b in batches))
    files_by_key: dict[str, list[str]] = defaultdict(list)
    total_assigned = 0
    for res in results:
        for path, keys in res.items():
            for k in keys:
                canon = resolve.get(_norm(k))
                if canon:
                    files_by_key[canon].append(path)
                    total_assigned += 1
    logger.info(
        "capability-first: %d capabilities, %d file-assignments for %s/%s", len(caps), total_assigned, owner, repo
    )
    # 割当が 1 件も取れないときは 0 機能へ退行させず、単発クラスタリングにフォールバックする（安全網）。
    if total_assigned == 0:
        logger.warning("capability-first produced no assignments for %s/%s; falling back to single-shot", owner, repo)
        return await cluster_features_agentic(paths, edges, owner=owner, repo=repo, descriptors=descriptors)

    clusters: list[dict] = []
    for c in caps:
        key = str(c["key"])
        # dedup while preserving order (a file may be assigned to the same key across batches).
        members = [{"path": p, "confidence": _ASSIGN_CONFIDENCE} for p in dict.fromkeys(files_by_key.get(key, []))]
        clusters.append(
            {
                "key": key,
                "name": str(c.get("name") or key),
                "description": str(c.get("description") or ""),
                "files": members,
            }
        )
    return clusters
