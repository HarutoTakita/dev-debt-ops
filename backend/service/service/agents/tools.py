"""Deterministic code-metric tools for agents (issue 069 Phase 0).

Thin, pure wrappers over ``services.code_analysis`` so an ``LlmAgent`` can call them as tools
(ADK auto-wraps plain callables passed in ``tools=[...]``). Determinism stays here — the agent
decides *which* files to feed and *how to interpret* the findings, not how the metrics compute.
More tools (complexity, blame/KC, AI-generation estimate) are added in later phases.
"""

from service.services import code_analysis


def list_source_files(paths: list[str]) -> list[str]:
    """Filter repository paths down to analysable source files.

    Drops vendored / non-source paths (``code_analysis.is_source_file``). Call this first to
    decide which files are worth fetching and analysing.

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
