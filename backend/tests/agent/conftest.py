"""Override root conftest fixtures for agent unit tests (no DB needed)."""

import pytest


@pytest.fixture(autouse=True)
def setup_db():
    """No-op override — agent tool tests use mocks and don't need a real DB."""
    return
