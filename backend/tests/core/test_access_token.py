"""EpochCheckedJWTStrategy unit test.

Isolated from the HTTP stack: the test bypasses the strategy's `super().read_token`
by patching it, then verifies the epoch branch returns the user when
`iat >= user.token_epoch` and `None` when `iat < user.token_epoch`.

End-to-end coverage of the logout → stale-access-token path lives in
`tests/api/v1/test_auth.py::test_logout_bumps_token_epoch`.
"""

import types
import uuid

import pytest
from pytest_mock import MockerFixture

from app.core.access_token import EpochCheckedJWTStrategy
from app.core.config import settings


def _user(token_epoch: int):
    """Build a user-like object with the fields the strategy touches."""
    return types.SimpleNamespace(id=uuid.uuid4(), token_epoch=token_epoch)


@pytest.fixture
def strategy() -> EpochCheckedJWTStrategy:
    return EpochCheckedJWTStrategy(secret=settings.SECRET_KEY.get_secret_value(), lifetime_seconds=300)


async def test_read_token_returns_user_when_iat_meets_epoch(
    strategy: EpochCheckedJWTStrategy, mocker: MockerFixture
) -> None:
    user = _user(token_epoch=0)
    mocker.patch.object(type(strategy).__bases__[0], "read_token", return_value=user)
    mocker.patch(
        "app.core.access_token.decode_jwt",
        return_value={"iat": 9_999_999_999, "sub": str(user.id)},
    )
    assert await strategy.read_token("fake-jwt", None) is user


async def test_read_token_returns_none_when_iat_below_epoch(
    strategy: EpochCheckedJWTStrategy, mocker: MockerFixture
) -> None:
    user = _user(token_epoch=2_000_000_000)
    mocker.patch.object(type(strategy).__bases__[0], "read_token", return_value=user)
    mocker.patch(
        "app.core.access_token.decode_jwt",
        return_value={"iat": 1_000_000_000, "sub": str(user.id)},
    )
    assert await strategy.read_token("fake-jwt", None) is None
