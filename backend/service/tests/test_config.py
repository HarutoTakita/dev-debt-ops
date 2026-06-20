"""Tests for the fail-closed worker auth config guard (issue-038)."""

import pytest

from service import config


def test_use_mock_queue_defaults_false(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without an explicit opt-in the mock queue (OIDC bypass) is off — fail-closed."""
    monkeypatch.delenv("USE_MOCK_QUEUE", raising=False)
    assert config.use_mock_queue() is False


def test_validate_runtime_config_rejects_mock_queue_in_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    """Enabling the mock queue outside dev must refuse to start."""
    monkeypatch.setenv("ENVIRONMENT", "prod")
    monkeypatch.setenv("USE_MOCK_QUEUE", "true")
    with pytest.raises(RuntimeError, match="USE_MOCK_QUEUE must be false outside dev"):
        config.validate_runtime_config()


def test_validate_runtime_config_allows_mock_queue_in_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    """Dev may opt into the mock queue."""
    monkeypatch.setenv("ENVIRONMENT", "dev")
    monkeypatch.setenv("USE_MOCK_QUEUE", "true")
    config.validate_runtime_config()  # no raise


def test_validate_runtime_config_allows_oidc_in_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prod with OIDC verification on (mock queue off) starts normally."""
    monkeypatch.setenv("ENVIRONMENT", "prod")
    monkeypatch.setenv("USE_MOCK_QUEUE", "false")
    config.validate_runtime_config()  # no raise
