"""Secret redaction for LLM inputs (issue 217 / 223).

Repository content (file bodies, tool results, agent-composed prompts) can contain credentials.
Before any such text reaches an LLM, we mask secrets so the model never receives them in plaintext.
Two complementary layers run (**defense in depth**):

1. **Rule-based** (this module's regexes) — fast, deterministic, structural: known token shapes
   (PEM / GitHub / Google / AWS / Slack / JWT), ``Bearer`` headers, and ``key=value`` secrets.
2. **detect-secrets** (Yelp) — entropy + a suite of specialised/keyword plugins, to catch
   high-entropy / novel secrets the regexes miss (issue 223). Runs after the regex layer and masks
   each detected secret value; graceful — any failure falls back to rule-based only.

Still not exhaustive (low-entropy / unusual secrets may slip), so pair it with not reading obvious
secret files (``.env`` / ``*.pem``) rather than relying on it as the only barrier.

Used by ``SecretRedactionPlugin`` (ADK runner), which scrubs every model request for the Twin Agent
and the agentified walkthrough / refactor / quiz pipelines at the single chokepoint where repo
content heads to Gemini.
"""

import logging
import re
from collections.abc import Iterable

from service import config

logger = logging.getLogger(__name__)

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


# detect-secrets layer tuning. High-entropy plugins are noisy (they flag short hex/base64 fragments
# like "FE"), so we only mask entropy hits at/above a real-secret length; keyword/specialised plugins
# are higher-confidence and mask at a lower floor. Bytes shorter than these are left alone so code
# isn't shredded by false positives.
_DS_ENTROPY_TYPES = frozenset({"Base64 High Entropy String", "Hex High Entropy String"})
_DS_ENTROPY_MIN_LEN = 20
_DS_MIN_LEN = 8


def _is_allowlisted(value: str, allowlist: frozenset[str]) -> bool:
    """True if ``value`` overlaps an allowlisted token (equal / substring either way).

    The allowlist carries caller-supplied known-safe identifiers — e.g. the repository owner / name /
    ``owner/repo`` / branch the agent is told to analyse. These are author-controlled, not secrets,
    but detect-secrets' entropy plugins flag slugs like ``owner/repo`` as high-entropy, which would
    mask the coordinates the agent needs to call its tools (issue 225). Substring matching also spares
    a flagged piece of an allowlisted token (e.g. just the owner out of ``owner/repo``).
    """
    return any(value in token or token in value for token in allowlist)


def _detect_secrets_pass(text: str, allowlist: frozenset[str]) -> tuple[str, int]:
    """Mask secrets found by detect-secrets (entropy + plugins); return ``(text, num_masked)``.

    Scans line by line under detect-secrets' default plugin/filter set, collects each detected
    secret value (length-gated to avoid masking short high-entropy noise, and allowlist-gated to
    avoid masking known-safe identifiers like the repo coordinates), and replaces every literal
    occurrence with the placeholder. Graceful: if detect-secrets is unavailable or errors, returns
    the text unchanged so the rule-based layer still applies and the model call never breaks.
    """
    try:
        from detect_secrets.core import scan
        from detect_secrets.settings import default_settings
    except Exception:  # pragma: no cover - import guard (dependency always present in service)
        return text, 0

    values: set[str] = set()
    try:
        with default_settings():
            for line in text.splitlines():
                for secret in scan.scan_line(line):
                    value = secret.secret_value
                    if not value or value in values or REDACTED in value:
                        continue
                    if _is_allowlisted(value, allowlist):
                        continue
                    floor = _DS_ENTROPY_MIN_LEN if secret.type in _DS_ENTROPY_TYPES else _DS_MIN_LEN
                    if len(value) >= floor:
                        values.add(value)
    except Exception:
        logger.warning("detect-secrets pass failed; falling back to rule-based redaction only", exc_info=True)
        return text, 0

    total = 0
    # Mask longest-first so a value that contains a shorter detected value is replaced whole.
    for value in sorted(values, key=len, reverse=True):
        text, count = re.subn(re.escape(value), REDACTED, text)
        total += count
    return text, total


def redact_secrets(text: str, *, allowlist: Iterable[str] = ()) -> tuple[str, int]:
    """Mask secrets in ``text``; return ``(redacted_text, num_redactions)``.

    Two layers run in order: (1) rule-based — standalone token patterns (masked wholesale),
    ``Bearer`` headers (scheme kept, credential masked), and assignment-style ``key=value`` secrets
    (key + separator kept, value masked); (2) detect-secrets — entropy/plugin detection for the
    high-entropy / novel secrets the regexes miss. ``num_redactions`` is the total substitutions made
    across both layers — advisory, for tracing / telemetry. Empty input returns ``(text, 0)``.

    ``allowlist`` is a set of known-safe literals (e.g. the repo owner / name / ``owner/repo`` /
    branch the agent is told to analyse) that the detect-secrets layer must never mask — its entropy
    plugins otherwise flag such slugs as secrets and strip the coordinates the agent needs (issue 225).
    """
    if not text:
        return text, 0
    allow = frozenset(token for token in allowlist if token)

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

    # Second layer: detect-secrets (entropy + plugins) over the already rule-masked text.
    text, count = _detect_secrets_pass(text, allow)
    total += count

    return text, total


# --- PII (rule-based, ローカル) — DLP 無効時・DLP 失敗時のフォールバック（issue 296）------------------
# 高確度なパターンのみ（コード中の識別子/数値の誤マスクを避ける）。汎用の電話/12桁番号は誤検知が多いため
# 日本の電話 + E.164 に限定し、マイナンバー等の文脈依存な型は DLP 有効時のみ（infoType）に任せる。
_EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
_IPV4_PATTERN = re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b")
_PHONE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b0[789]0-?\d{4}-?\d{4}\b"),  # 日本の携帯
    re.compile(r"\b0\d{1,3}-\d{1,4}-\d{4}\b"),  # 日本の固定（ハイフン必須で誤検知を抑制）
    re.compile(r"\+\d{10,15}\b"),  # E.164
)
_CARD_CANDIDATE = re.compile(r"\b(?:\d[ -]?){13,19}\b")  # クレカ候補（Luhn 検証を通ったものだけマスク）


def _luhn_ok(digits: str) -> bool:
    """Luhn チェックサム（クレジットカードの誤検知抑制用）を検証する."""
    total, alt = 0, False
    for ch in reversed(digits):
        d = ord(ch) - 48
        if alt:
            d = d * 2 - 9 if d * 2 > 9 else d * 2
        total += d
        alt = not alt
    return total % 10 == 0


def redact_pii_rulebased(text: str) -> tuple[str, int]:
    """メール / 電話(日本・E.164) / クレジットカード(Luhn) / IPv4 を正規表現でマスクし ``(text, 件数)`` を返す.

    ローカルで完結（外部 API 不使用）。DLP 無効時と DLP 失敗時のフォールバックとして使う。
    """
    if not text:
        return text, 0
    total = 0
    text, c = _EMAIL_PATTERN.subn("[EMAIL]", text)
    total += c
    for pat in _PHONE_PATTERNS:
        text, c = pat.subn("[PHONE]", text)
        total += c
    text, c = _IPV4_PATTERN.subn("[IP]", text)
    total += c

    n_card = 0

    def _card(m: re.Match[str]) -> str:
        nonlocal n_card
        digits = re.sub(r"\D", "", m.group(0))
        if 13 <= len(digits) <= 19 and _luhn_ok(digits):
            n_card += 1
            return "[CARD]"
        return m.group(0)

    text = _CARD_CANDIDATE.sub(_card, text)
    return text, total + n_card


async def deidentify(text: str, *, allowlist: Iterable[str] = ()) -> tuple[str, int]:
    """LLM 送信前の統合マスキング（issue 296）。``(masked_text, 件数)`` を返す.

    - **シークレット**は常にローカル（``redact_secrets`` = 正規表現＋detect-secrets）。
    - **PII** は ``DLP_ENABLED=true`` のときだけ Cloud DLP（``services.dlp.deidentify_pii``）、無効時と
      **DLP 失敗時はローカルのルールベース**（``redact_pii_rulebased``）にフォールバックする。

    ADK（``SecretRedactionPlugin``）と直呼び（``gemini_stack_service._generate``）の両経路の唯一の入口。
    """
    if not text:
        return text, 0
    allow = frozenset(token for token in allowlist if token)
    text, n_secrets = redact_secrets(text, allowlist=allow)
    if config.dlp_enabled():
        try:
            from service.services import dlp

            text, n_pii = await dlp.deidentify_pii(text, allowlist=allow)
        except Exception:
            logger.warning("Cloud DLP de-identify failed; falling back to rule-based PII masking", exc_info=True)
            text, n_pii = redact_pii_rulebased(text)
    else:
        text, n_pii = redact_pii_rulebased(text)
    return text, n_secrets + n_pii
