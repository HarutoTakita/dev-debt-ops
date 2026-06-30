"""Unit tests for secret redaction (issue 217).

Covers ``redact_secrets`` (token shapes, Bearer headers, assignment-style secrets, idempotency,
non-secret text left intact) and ``SecretRedactionPlugin`` masking an outgoing model request in
place via fakes — no DB / network / live model needed.
"""

import pytest

from service.agents.plugin import SecretRedactionPlugin
from service.services.secret_redaction import REDACTED, redact_secrets

# --- redact_secrets: standalone token shapes -------------------------------


@pytest.mark.parametrize(
    "secret",
    [
        "ghp_" + "a" * 36,  # GitHub classic PAT
        "gho_" + "b" * 36,  # GitHub OAuth token
        "github_pat_" + "c" * 40,  # GitHub fine-grained PAT
        "AIza" + "D" * 35,  # Google API key
        "AKIA" + "E" * 16,  # AWS access key id
        "xoxb-" + "1" * 20,  # Slack bot token
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c",  # JWT
    ],
)
def test_redact_secrets_masks_known_token_shapes(secret: str) -> None:
    """Each high-confidence token shape is masked and counted exactly once."""
    redacted, count = redact_secrets(f"token is {secret} here")
    assert secret not in redacted
    assert REDACTED in redacted
    assert count == 1


def test_redact_secrets_masks_pem_private_key_block() -> None:
    """A PEM private key block is masked header-to-footer as a single redaction."""
    text = "key:\n-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA\n-----END RSA PRIVATE KEY-----\n"
    redacted, count = redact_secrets(text)
    assert "MIIEowIBAAKCAQEA" not in redacted
    assert "PRIVATE KEY" not in redacted
    assert count == 1


def test_redact_secrets_masks_bearer_but_keeps_scheme() -> None:
    """A Bearer credential is masked while the ``Bearer`` scheme is preserved."""
    redacted, count = redact_secrets("Authorization: Bearer abcdef0123456789ABCDEF")
    assert "abcdef0123456789ABCDEF" not in redacted
    assert "Bearer" in redacted
    assert REDACTED in redacted
    assert count == 1


# --- redact_secrets: assignment-style secrets ------------------------------


@pytest.mark.parametrize(
    "line",
    [
        'api_key = "s3cr3t_value_here"',
        "DB_PASSWORD=hunter2_longvalue",
        "client_secret: abcdef123456",
        "AUTH_TOKEN = 'xyz789longenough'",
    ],
)
def test_redact_secrets_masks_assignment_values(line: str) -> None:
    """Secret-looking ``key=value`` lines keep the key/separator but mask the value."""
    redacted, count = redact_secrets(line)
    key = line.split("=")[0].split(":")[0].strip()
    assert key in redacted  # key + separator preserved
    assert REDACTED in redacted
    assert count == 1


def test_redact_secrets_leaves_non_secret_text_intact() -> None:
    """Ordinary prose / code without secrets is returned unchanged with a zero count."""
    text = "def add(a, b):\n    return a + b  # simple helper\n"
    redacted, count = redact_secrets(text)
    assert redacted == text
    assert count == 0


def test_redact_secrets_is_idempotent() -> None:
    """Re-running redaction over already-masked text makes no further substitutions."""
    once, first = redact_secrets("token: ghp_" + "z" * 36)
    twice, second = redact_secrets(once)
    assert twice == once
    assert first == 1
    assert second == 0


def test_redact_secrets_empty_input() -> None:
    """Empty input returns unchanged with a zero count."""
    assert redact_secrets("") == ("", 0)


# --- detect-secrets layer (issue 223) --------------------------------------


def test_detect_secrets_catches_high_entropy_value_rules_miss() -> None:
    """A high-entropy value under a non-secret key (rule layer misses it) is masked by detect-secrets."""
    # Canonical AWS doc example secret-access-key; key "config" is NOT secret-like, so the
    # assignment regex does not match and there is no known prefix — only detect-secrets catches it.
    secret = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
    redacted, count = redact_secrets(f'config = "{secret}"')
    assert secret not in redacted
    assert REDACTED in redacted
    assert count >= 1


def test_detect_secrets_ignores_short_high_entropy_noise() -> None:
    """Short high-entropy fragments (e.g. a 2-char hex) are below the floor and left intact."""
    text = "color = 0xFE\nstep = 0x1\n"
    redacted, count = redact_secrets(text)
    assert redacted == text
    assert count == 0


def test_detect_secrets_flags_owner_repo_slug_without_allowlist() -> None:
    """Regression guard (issue 225): the entropy plugin flags an ``owner/repo`` slug as a secret."""
    prompt = "リポジトリ HarutoTakita/cyber-tech のブランチ main を分析"
    redacted, count = redact_secrets(prompt)
    assert "HarutoTakita/cyber-tech" not in redacted
    assert count >= 1


def test_allowlist_preserves_repo_coordinates() -> None:
    """With the repo coords allowlisted, the agent's prompt keeps ``owner/repo`` intact (issue 225)."""
    prompt = "リポジトリ HarutoTakita/cyber-tech のブランチ main を分析"
    allow = {"HarutoTakita", "cyber-tech", "HarutoTakita/cyber-tech", "main"}
    redacted, count = redact_secrets(prompt, allowlist=allow)
    assert "HarutoTakita/cyber-tech" in redacted
    assert count == 0


def test_allowlist_still_masks_real_secret() -> None:
    """Allowlisting repo coords does not weaken masking of an actual secret in the same text."""
    secret = "ghp_" + "a" * 36
    redacted, count = redact_secrets(
        f"repo HarutoTakita/cyber-tech token {secret}", allowlist={"HarutoTakita/cyber-tech"}
    )
    assert "HarutoTakita/cyber-tech" in redacted
    assert secret not in redacted
    assert count >= 1


# --- SecretRedactionPlugin -------------------------------------------------


class _FakePart:
    def __init__(self, text: str | None) -> None:
        self.text = text


class _FakeContent:
    def __init__(self, parts: list[_FakePart]) -> None:
        self.parts = parts


class _FakeLlmRequest:
    def __init__(self, contents: list[_FakeContent]) -> None:
        self.contents = contents


async def test_plugin_masks_request_parts_in_place() -> None:
    """before_model_callback masks every secret-bearing text part in place and counts them."""
    parts = [_FakePart("see ghp_" + "q" * 36), _FakePart("password=supersecretvalue"), _FakePart("plain text")]
    request = _FakeLlmRequest([_FakeContent(parts)])
    plugin = SecretRedactionPlugin()

    result = await plugin.before_model_callback(callback_context=object(), llm_request=request)

    assert result is None  # proceed with the (mutated) request
    assert "ghp_" not in parts[0].text
    assert "supersecretvalue" not in parts[1].text
    assert parts[2].text == "plain text"  # untouched
    assert plugin.redacted == 2


async def test_plugin_handles_empty_contents() -> None:
    """A request with no contents is a no-op (no error, nothing redacted)."""
    plugin = SecretRedactionPlugin()
    result = await plugin.before_model_callback(callback_context=object(), llm_request=_FakeLlmRequest([]))
    assert result is None
    assert plugin.redacted == 0
