"""Knowledge-debt detection helpers (issue 030) — pure, deterministic.

Decide the three knowledge-debt reasons from already-fetched per-file signals:
- ``ai_generated``: Gemini AI-generation probability over a threshold.
- ``author_left``: the file's latest commit is older than a staleness threshold (MVP proxy for
  "main author left / knowledge gone stale"; true org-departure detection is deferred).
- ``no_review``: the file's latest commit belongs to no reviewed pull request (direct push or
  unreviewed/auto-approved merge).

Scores feed ``code_analysis.quantize_severity`` (shared 4-band thresholds, issue 028).
"""

_AUTHOR_LEFT_DAYS = 180  # latest commit older than this → author_left (MVP proxy)
_AUTHOR_LEFT_SPAN_DAYS = 730.0  # age mapped over this span into 0..1 for severity
_AI_THRESHOLD = 0.5  # Gemini probability at/above which a file is ai_generated
_NO_REVIEW_SCORE = 0.6  # fixed score for an unreviewed merge (→ high severity)


def is_ai_generated(ai_prob: float) -> bool:
    """Whether the Gemini AI-generation probability flags the file as ai_generated."""
    return ai_prob >= _AI_THRESHOLD


def is_author_left(age_days: int) -> bool:
    """Whether the file's latest commit is stale enough to flag author_left (MVP proxy)."""
    return age_days >= _AUTHOR_LEFT_DAYS


def author_left_score(age_days: int) -> float:
    """Map latest-commit age (days) into a 0..1 severity score."""
    return max(0.0, min(1.0, age_days / _AUTHOR_LEFT_SPAN_DAYS))


def is_no_review(pull_numbers: list[int], reviewed_pulls: set[int]) -> bool:
    """True if the commit has no PR (direct push) or none of its PRs were reviewed/approved."""
    if not pull_numbers:
        return True
    return all(number not in reviewed_pulls for number in pull_numbers)


def reason_score(reason: str, *, ai_prob: float, age_days: int) -> float:
    """The 0..1 score a reason contributes (severity is quantized from this)."""
    if reason == "ai_generated":
        return ai_prob
    if reason == "author_left":
        return author_left_score(age_days)
    if reason == "no_review":
        return _NO_REVIEW_SCORE
    return 0.0
