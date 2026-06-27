"""Code-walkthrough generation core (shared by the on-demand pipeline and learning-plan pre-generation).

Fetches a file from GitHub and asks Gemini for an ordered, line-anchored walkthrough, then re-anchors the
line numbers to the real file via each step's ``start_text`` so the highlight matches the explanation.
"""

import logging

import httpx

from service.services import gemini_stack_service
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
