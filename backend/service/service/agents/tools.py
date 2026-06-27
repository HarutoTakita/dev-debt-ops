"""Deterministic tools for agents (issue 069).

Two kinds live here:

- Pure metric helpers over ``services.code_analysis`` (``list_source_files`` /
  ``duplication_findings`` / ``dead_file_findings``) — usable directly in tests.
- ``build_repo_tools`` — closures over a ``GitHubGitClient`` + ``RunBudget`` that an
  ``LlmAgent`` calls to explore a repository (list / read / assess). The agent decides *which*
  files to read and *how to interpret* findings; the metrics themselves stay deterministic.
"""

from collections.abc import Callable
from typing import Any

from service.agents.budget import RunBudget
from service.services import code_analysis
from service.services.github_git_client import GitHubGitClient

_MAX_AGENT_FILES = 20
_MAX_FILE_CHARS = 5_000


def list_source_files(paths: list[str]) -> list[str]:
    """Filter repository paths down to analysable source files.

    Drops vendored / non-source paths (``code_analysis.is_source_file``).

    Args:
        paths: Repository-relative file paths (e.g. from the file tree).

    Returns:
        The subset that are source files.
    """
    return [path for path in paths if code_analysis.is_source_file(path)]


def duplication_findings(files: dict[str, str]) -> list[dict[str, object]]:
    """Detect near-duplicate files and return them as code-debt findings.

    Args:
        files: Mapping of file path to text content for the snapshot.

    Returns:
        One finding per file whose duplicate ratio crosses the debt threshold, with
        ``file_path``, ``duplicate_ratio`` and a normalised ``score``.
    """
    findings: list[dict[str, object]] = []
    for path, ratio in code_analysis.find_duplicate_ratios(files).items():
        if code_analysis.duplication_is_debt(ratio):
            findings.append(
                {
                    "file_path": path,
                    "duplicate_ratio": round(ratio, 3),
                    "score": code_analysis.duplication_score(ratio),
                }
            )
    return findings


def dead_file_findings(files: dict[str, str]) -> list[str]:
    """Return source files that appear unreferenced (dead code) within the snapshot.

    Args:
        files: Mapping of file path to text content for the snapshot.

    Returns:
        Sorted list of file paths with no inbound references.
    """
    return sorted(code_analysis.find_dead_files(files))


def build_repo_tools(client: GitHubGitClient, budget: RunBudget) -> list[Callable[..., Any]]:
    """Build the repository-exploration tools an ``LlmAgent`` calls during analysis.

    Closures capture the authenticated GitHub client + the run budget. Tool-call counting is
    enforced by the before-tool callback (``service.agents.hooks``); here ``read_file`` also
    charges the file-read budget. Returns ``[list_repo_source_files, read_file, assess_code_debt]``.
    """

    async def list_repo_source_files(owner: str, repo: str, branch: str = "main") -> list[str]:
        """List analysable source files in a repository (excludes vendored/config files).

        Call this first to decide which files are worth reading. Capped to keep the run bounded.

        Args:
            owner: Repository owner or organisation.
            repo: Repository name.
            branch: Branch to scan (defaults to main).

        Returns:
            Source file paths (at most the per-run cap).
        """
        tree = await client.get_repository_tree(owner, repo, branch)
        sources = [item.path for item in tree if item.type == "blob" and code_analysis.is_source_file(item.path)]
        return sources[:_MAX_AGENT_FILES]

    async def read_file(owner: str, repo: str, path: str, ref: str = "main") -> str:
        """Read one file's text content (truncated). Charges the file-read budget.

        Args:
            owner: Repository owner or organisation.
            repo: Repository name.
            path: File path within the repository.
            ref: Git ref to read from (branch / tag / sha).

        Returns:
            The file content, truncated to a safe length.
        """
        budget.charge_files(1)
        file_content = await client.get_file_content(owner, repo, path, ref)
        content = file_content.content or ""
        if len(content) > _MAX_FILE_CHARS:
            return content[:_MAX_FILE_CHARS] + "\n... (truncated)"
        return content

    async def assess_code_debt(path: str, content: str) -> dict[str, object]:
        """Compute deterministic code-debt signals for one file (cyclomatic complexity).

        Use this to judge whether a file you read carries technical debt; combine across files
        to decide which feature is riskiest. The metric is deterministic — your job is the
        judgement, not the calculation.

        Args:
            path: File path (used to detect the language).
            content: The file's text content.

        Returns:
            ``{path, language, cyclomatic_complexity, is_complexity_debt, complexity_score}``.
        """
        language = code_analysis._language(path) or ""
        complexity = code_analysis.cyclomatic_complexity(content, language) if language else 0
        return {
            "path": path,
            "language": language,
            "cyclomatic_complexity": complexity,
            "is_complexity_debt": code_analysis.complexity_is_debt(complexity),
            "complexity_score": code_analysis.complexity_score(complexity),
        }

    return [list_repo_source_files, read_file, assess_code_debt]
