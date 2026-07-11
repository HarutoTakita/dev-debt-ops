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
import re

import httpx

from service.agents.budget import RunBudget
from service.agents.serena_mcp import build_serena_toolset
from service.agents.single_agent import run_single_agent
from service.agents.walkthrough_agent import build_walkthrough_agent
from service.services import code_analysis, gemini_stack_service, repo_checkout
from service.services.github_git_client import GitHubGitClient

logger = logging.getLogger(__name__)

_ANCHOR_WINDOW = 5  # 複数一致時に LLM の claim をどれだけ信じて最近傍を選ぶか（行数）。超過は曖昧として drop。
_SYMBOL_SNAP_WINDOW = 3  # step が def の直下から始まる ⇒ その関数/クラス全体を指すと見なす許容行数


def _snap_range(
    start: int, end: int, symbols: list[tuple[int, int, int]], stripped: list[str], n: int
) -> tuple[int, int]:
    """Widen an anchored highlight so it isn't misleadingly narrow. Only ever *widens* the range.

    1. If the step begins at/just-below a symbol's ``def`` line, snap to the whole symbol (incl. its
       leading comment/decorator block) — a step about a function should highlight the whole function,
       not its first line. Genuinely granular sub-steps (start well inside a body) are left as-is.
    2. If the range covers only comment/blank lines, extend down to the first real statement (a
       documenting comment on its own is not a useful highlight).
    """
    best: tuple[int, int, int] | None = None
    for def_line, block_start, end_line in symbols:
        if def_line <= start <= def_line + _SYMBOL_SNAP_WINDOW and (best is None or def_line > best[0]):
            best = (def_line, block_start, end_line)
    if best is not None:
        _, block_start, end_line = best
        start, end = min(start, block_start), max(end, end_line)
    if all((not stripped[i - 1]) or stripped[i - 1].startswith("#") for i in range(start, end + 1)):
        j = end  # 0-based index of 1-based line (end + 1); scan for the first real statement below
        while j < n and ((not stripped[j]) or stripped[j].startswith("#")):
            j += 1
        if j < n:
            end = j + 1
    return start, end


def clean_steps(raw: list[dict], lines: list[str], path: str = "") -> list[dict]:
    """Validate steps, re-anchor line numbers to the real file via ``start_text``, clamp, keep order.

    LLMs miscount line numbers, so we snap ``start_line`` to the file line whose content matches the
    returned ``start_text`` (closest occurrence to the claim) and shift ``end_line`` by the same delta.
    For Python files (``path`` ends with ``.py``) we additionally widen the range to the whole enclosing
    symbol and extend comment-only ranges to the statement they document (see ``_snap_range``) — this fixes
    highlights that landed on 関数冒頭数行 / コメントのみ. Falls back to the clamped claim otherwise.
    """
    n = len(lines)
    stripped = [ln.strip() for ln in lines]
    symbols = code_analysis.python_symbol_spans("\n".join(lines)) if path.endswith(".py") else []
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
        # 誤ったハイライトは欠落より有害なので、曖昧/未検証な anchor は行番号 claim を信じず step ごと drop
        # する（issue 074-F）。防御的に残った ``N: `` プレフィックスは除去してから照合する。
        anchor = re.sub(r"^\s*\d+:\s?", "", str(item.get("start_text") or "")).strip()
        if anchor:
            matches = [i + 1 for i, s in enumerate(stripped) if s and s == anchor]
            if len(matches) == 1:
                best = matches[0]  # 一意一致 → テキストは行番号より確実。距離に依らず採用。
            elif len(matches) > 1:
                best = min(matches, key=lambda line_no: abs(line_no - start))
                if abs(best - start) > _ANCHOR_WINDOW:
                    continue  # 複数一致かつ claim が遠い → どれか判定できず drop。
            else:
                continue  # anchor が本文に存在しない → 検証不能につき drop。
            end += best - start
            start = best
        start = max(1, min(start, n))
        end = max(start, min(end, n))
        if symbols:
            start, end = _snap_range(start, end, symbols, stripped, n)
        out.append(
            {
                "start_line": start,
                "end_line": end,
                "title": str(item.get("title") or "").strip(),
                "explanation": explanation,
            }
        )
    # 先頭ステップが「モジュール docstring / import だけ」を指すと、学習画面の初期表示が実装コードではなく
    # 自然言語プロースになる。実装が始まる行より前で完結するステップは先頭から落とす（最低 1 つは残す）。
    boundary = code_analysis.leading_code_line("\n".join(lines))
    if boundary > 1:
        trimmed = [s for s in out if s["end_line"] >= boundary]
        if trimmed:
            out = trimmed
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
    return clean_steps(raw, file.content.split("\n"), path)


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

    return clean_steps(raw, file.content.split("\n"), path)
