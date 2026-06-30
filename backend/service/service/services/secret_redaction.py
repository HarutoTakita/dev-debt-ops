"""Secret redaction for LLM inputs (issue 217).

Repository content (file bodies, tool results, agent-composed prompts) can contain credentials.
Before any such text reaches an LLM, we mask common secret shapes so the model never receives them
in plaintext. This is **defense in depth** — pattern + assignment based, so novel or low-entropy
secrets may slip through; it reduces, not eliminates, exposure. Pair it with not reading obvious
secret files (``.env`` / ``*.pem``) rather than relying on it as the only barrier.

Used by ``SecretRedactionPlugin`` (ADK runner), which scrubs every model request for the Twin Agent
and the agentified walkthrough / refactor / quiz pipelines at the single chokepoint where repo
content heads to Gemini.
"""

import re

# What a masked secret is replaced with. The guillemets are excluded from the assignment value
# class below so a second pass never re-masks an already-masked value (keeps the count honest).
REDACTED = "«REDACTED»"

# High-confidence standalone token shapes — masked wholesale wherever they appear. Bounds on the
# variable parts keep each pattern linear (no catastrophic backtracking) while matching real tokens.
_TOKEN_PATTERNS: tuple[re.Pattern[str], ...] = (
    # PEM private key blocks (RSA/EC/OPENSSH/…), header to footer.
    re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----", re.DOTALL),
    # GitHub tokens: ghp_/gho_/ghu_/ghs_/ghr_ (classic+OAuth) and fine-grained github_pat_…
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    # Google API key.
    re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),
    # AWS access key id.
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    # Slack tokens (bot/user/app/refresh/…).
    re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}\b"),
    # JWT (three base64url segments).
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
)

# ``Authorization: Bearer <token>`` — keep the scheme, mask the credential.
_BEARER_PATTERN = re.compile(r"(?i)\b(bearer)\s+([A-Za-z0-9._\-]{16,})")

# Assignment-style secrets: a key whose name looks secret, then ``:`` or ``=``, then a value.
# The key + separator (+ optional quote) are kept; only the value is masked. The value class
# excludes whitespace, quotes, ``#`` (comments) and the guillemets used by REDACTED.
_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)(?P<key>[\w.\-]{0,40}?"
    r"(?:passwd|password|secret|api[_-]?key|access[_-]?key|client[_-]?secret|"
    r"auth[_-]?token|credentials?|token)[\w.\-]*)"
    r"(?P<sep>\s*[:=]\s*)"
    r"(?P<quote>[\"']?)"
    r"(?P<value>[^\s\"'#«»]{6,})"
    r"(?P=quote)"
)


def redact_secrets(text: str) -> tuple[str, int]:
    """Mask common secret shapes in ``text``; return ``(redacted_text, num_redactions)``.

    Applies, in order: standalone token patterns (masked wholesale), ``Bearer`` headers (scheme
    kept, credential masked), and assignment-style ``key=value`` secrets (key + separator kept,
    value masked). ``num_redactions`` is the total number of substitutions made — advisory, for
    tracing / telemetry. Non-string or empty input returns ``(text, 0)`` unchanged.
    """
    if not text:
        return text, 0

    total = 0
    for pattern in _TOKEN_PATTERNS:
        text, count = pattern.subn(REDACTED, text)
        total += count

    text, count = _BEARER_PATTERN.subn(rf"\1 {REDACTED}", text)
    total += count

    def _mask_value(match: re.Match[str]) -> str:
        quote = match.group("quote")
        return f"{match.group('key')}{match.group('sep')}{quote}{REDACTED}{quote}"

    text, count = _ASSIGNMENT_PATTERN.subn(_mask_value, text)
    total += count

    return text, total
