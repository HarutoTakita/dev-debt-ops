"""GitHub rate-limit → transient error hook (issue-045)."""

import httpx
import pytest

from service.services.github_git_client import _raise_on_rate_limit
from shared.worker import TransientTaskError


async def test_429_raises_transient() -> None:
    with pytest.raises(TransientTaskError):
        await _raise_on_rate_limit(httpx.Response(429, headers={"retry-after": "60"}))


async def test_403_with_zero_remaining_raises_transient() -> None:
    with pytest.raises(TransientTaskError):
        await _raise_on_rate_limit(httpx.Response(403, headers={"x-ratelimit-remaining": "0"}))


async def test_plain_403_does_not_raise() -> None:
    # A permission error (no rate-limit signal) must stay a permanent failure, not a retry.
    await _raise_on_rate_limit(httpx.Response(403))


async def test_200_does_not_raise() -> None:
    await _raise_on_rate_limit(httpx.Response(200))
