"""Code-walkthrough generation core (shared by the on-demand pipeline and learning-plan pre-generation).

Fetches a file from GitHub and produces an ordered, line-anchored walkthrough, then re-anchors the
line numbers to the real file via each step's ``start_text`` so the highlight matches the explanation.

Two producers share the cleaning/anchoring logic:
- ``build_walkthrough`` — a single direct Gemini call (fast; used by learning-plan pre-generation).
- ``build_walkthrough_agentic`` — an ADK agent that follows referenced symbols via Serena for a
  deeper explanation (issue 217 PR2; used by the on-demand pipeline), with fallback to the direct
  path on any failure so behaviour degrades gracefully.
"""

import logging

import httpx

from service.agents.budget import RunBudget
from service.agents.serena_mcp import build_serena_toolset
from service.agents.single_agent import run_single_agent
from service.agents.walkthrough_agent import build_walkthrough_agent
from service.services import gemini_stack_service, repo_checkout
from service.services.github_git_client import GitHubGitClient

logger = logging.getLogger(__name__)


def clean_steps(raw: list[dict], lines: list[str]) -> list[dict]:
    """Validate steps, re-anchor line numbers to the real file via ``start_text``, clamp, keep order.

    LLMs miscount line numbers, so we snap ``start_line`` to the file line whose content matches the
    returned ``start_text`` (closest occurrence to the claim) and shift ``end_line`` by the same delta.
    This keeps the highlighted range aligned with the explanation. Falls back to the clamped claim.
    """
    n = len(lines)
    stripped = [ln.strip() for ln in lines]
    out: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        start_raw = item.get("start_line")
        end_raw = item.get("end_line")
        if start_raw is None or end_raw is None:
            continue
        try:
            start = int(start_raw)
            end = int(end_raw)
        except (TypeError, ValueError):
            continue
        explanation = str(item.get("explanation") or "").strip()
        if not explanation:
            continue
        # Re-anchor by matching the exact start-line text to the real file (corrects LLM line drift).
        anchor = str(item.get("start_text") or "").strip()
        if anchor:
            matches = [i + 1 for i, s in enumerate(stripped) if s and s == anchor]
            if matches:
                best = min(matches, key=lambda line_no: abs(line_no - start))
                end += best - start
                start = best
        start = max(1, min(start, n))
        end = max(start, min(end, n))
        out.append(
            {
                "start_line": start,
                "end_line": end,
                "title": str(item.get("title") or "").strip(),
                "explanation": explanation,
            }
        )
    return out


async def build_walkthrough(client: GitHubGitClient, owner: str, repo: str, path: str, ref: str) -> list[dict]:
    """Fetch a file and generate its cleaned, line-anchored walkthrough. Empty list on any failure."""
    try:
        file = await client.get_file_content(owner, repo, path, ref)
    except httpx.HTTPError:
        logger.warning("code-walkthrough: could not fetch %s", path)
        return []
    if not file.content:
        return []
    try:
        raw = await gemini_stack_service.generate_code_walkthrough(path, file.content)
    except ValueError:
        logger.warning("Gemini code-walkthrough unavailable for %s", path)
        return []
    return clean_steps(raw, file.content.split("\n"))


def _numbered(content: str) -> str:
    """Render file content with 1-based ``N: `` line-number prefixes (matches the direct prompt)."""
    return "\n".join(f"{i + 1}: {line}" for i, line in enumerate(content.split("\n")))


async def _run_walkthrough_agent(owner: str, repo: str, path: str, ref: str, content: str, token: str) -> list[dict]:
    """Drive the walkthrough agent over one file; return the steps it saved (``[]`` if none).

    Shallow-clones the repo so Serena (LSP) can follow referenced symbols, runs the agent via
    ``run_single_agent`` (trace + secret-redaction plugins), and always deletes the clone. If the
    clone fails the agent still runs from the numbered prompt alone (Serena simply absent).
    """
    repo_dir = await repo_checkout.shallow_clone(owner, repo, ref, token)
    serena = build_serena_toolset(repo_dir) if repo_dir else None
    captured: list[dict] = []
    agent = build_walkthrough_agent(
        path=path,
        budget=RunBudget(),
        captured=captured,
        serena_toolset=serena,
    )
    prompt = f"ファイル「{path}」の全文（行番号つき）:\n\n{_numbered(content)}"
    try:
        await run_single_agent(
            agent=agent,
            prompt=prompt,
            user_id=f"{owner}_{repo}",
            toolsets=[serena] if serena else None,
            redaction_allowlist=[owner, repo, f"{owner}/{repo}", ref, path],
        )
    finally:
        if repo_dir:
            repo_checkout._cleanup(repo_dir)
    return captured


async def build_walkthrough_agentic(
    client: GitHubGitClient, owner: str, repo: str, path: str, ref: str, *, token: str
) -> list[dict]:
    """Agentic walkthrough for one file, with fallback to the direct path (issue 217 PR2).

    The agent reads the file and follows referenced symbols via Serena, then saves line-anchored
    steps. On any failure or an empty result it falls back to ``generate_code_walkthrough`` (the
    direct Gemini call), so behaviour never regresses below the non-agentic path. Returns the
    cleaned, re-anchored steps (empty list if the file can't be fetched / has no content).
    """
    try:
        file = await client.get_file_content(owner, repo, path, ref)
    except httpx.HTTPError:
        logger.warning("code-walkthrough(agentic): could not fetch %s", path)
        return []
    if not file.content:
        return []

    raw: list[dict] = []
    try:
        raw = await _run_walkthrough_agent(owner, repo, path, ref, file.content, token)
    except Exception as exc:  # any agent/runtime failure → fall back to the direct path
        logger.warning("code-walkthrough(agentic) failed for %s: %s; falling back to direct", path, exc)

    if not raw:
        try:
            raw = await gemini_stack_service.generate_code_walkthrough(path, file.content)
        except ValueError:
            logger.warning("Gemini code-walkthrough unavailable for %s", path)
            return []

    return clean_steps(raw, file.content.split("\n"))
