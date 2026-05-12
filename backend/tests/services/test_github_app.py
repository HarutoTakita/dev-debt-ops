"""GitHubAppService ユニットテスト。

JWT 生成・トークンキャッシュ・有効期限管理を HTTP 呼び出しなしで検証する。
"""

import time
from unittest.mock import AsyncMock, MagicMock

import jwt
import pytest
from pytest_mock import MockerFixture

from app.services.github_app import GitHubAppService, _to_pem


@pytest.fixture
def service(rsa_key_pair) -> GitHubAppService:
    pem, _ = rsa_key_pair
    return GitHubAppService(app_id="123456", private_key=pem)


def _mock_response(json_data: dict) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = json_data
    return resp


def _mock_http_client(resp: MagicMock, method: str = "post") -> MagicMock:
    """async with httpx.AsyncClient() as client: client.{method}(...) のモックを返す。"""
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    setattr(client, method, AsyncMock(return_value=resp))
    return client


# ---------------------------------------------------------------------------
# _to_pem
# ---------------------------------------------------------------------------


class TestToPem:
    def test_already_pem_returned_as_is(self):
        pem = "-----BEGIN RSA PRIVATE KEY-----\nABC\n-----END RSA PRIVATE KEY-----"
        assert _to_pem(pem) == pem

    def test_raw_base64_wrapped_with_headers(self):
        raw = "ABCDEFGHIJKLMNOPabcdefghijklmnop"
        result = _to_pem(raw)
        assert result.startswith("-----BEGIN RSA PRIVATE KEY-----")
        assert result.endswith("-----END RSA PRIVATE KEY-----")
        assert raw in result

    def test_escaped_newlines_converted_to_real_newlines(self):
        pem = "-----BEGIN RSA PRIVATE KEY-----\\nABC\\n-----END RSA PRIVATE KEY-----"
        result = _to_pem(pem)
        assert "\\n" not in result
        assert "\n" in result

    def test_leading_trailing_whitespace_stripped(self):
        pem = "  -----BEGIN RSA PRIVATE KEY-----\nABC\n-----END RSA PRIVATE KEY-----  "
        result = _to_pem(pem)
        assert result.startswith("-----BEGIN RSA PRIVATE KEY-----")


# ---------------------------------------------------------------------------
# _create_jwt
# ---------------------------------------------------------------------------


class TestCreateJwt:
    def test_uses_rs256_algorithm(self, service: GitHubAppService):
        token = service._create_jwt()
        assert jwt.get_unverified_header(token)["alg"] == "RS256"

    def test_payload_contains_required_fields(self, service: GitHubAppService, rsa_key_pair):
        _, public_key = rsa_key_pair
        token = service._create_jwt()
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            options={"verify_aud": False},
        )
        now = int(time.time())
        assert payload["iss"] == "123456"
        assert payload["iat"] <= now
        assert payload["exp"] > now

    def test_exp_is_about_10_minutes_after_iat(self, service: GitHubAppService, rsa_key_pair):
        _, public_key = rsa_key_pair
        token = service._create_jwt()
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            options={"verify_aud": False},
        )
        # iat に 60秒スキューがあるため exp - iat は 660秒前後になる
        assert 600 <= payload["exp"] - payload["iat"] <= 660


# ---------------------------------------------------------------------------
# _get_cached_token
# ---------------------------------------------------------------------------


class TestGetCachedToken:
    def test_miss_when_no_entry(self, service: GitHubAppService):
        assert service._get_cached_token(9999) is None

    def test_hit_when_valid_cache(self, service: GitHubAppService):
        far_future = time.time() + 3600
        service._token_cache[1] = ("valid_token", far_future)
        assert service._get_cached_token(1) == "valid_token"

    def test_miss_when_token_expired(self, service: GitHubAppService):
        past = time.time() - 1
        service._token_cache[2] = ("expired_token", past)
        assert service._get_cached_token(2) is None

    def test_miss_when_within_expiry_buffer(self, service: GitHubAppService):
        # 残り 200 秒 < バッファ 300 秒 → 再取得が必要
        soon = time.time() + 200
        service._token_cache[3] = ("almost_expired", soon)
        assert service._get_cached_token(3) is None


# ---------------------------------------------------------------------------
# get_installation_token
# ---------------------------------------------------------------------------


class TestGetInstallationToken:
    async def test_calls_github_api_and_returns_token(
        self, service: GitHubAppService, mocker: MockerFixture
    ):
        resp = _mock_response({"token": "ghs_test", "expires_at": "2099-01-01T00:00:00Z"})
        mock_client = _mock_http_client(resp, method="post")
        mocker.patch("app.services.github_app.httpx.AsyncClient", return_value=mock_client)

        token = await service.get_installation_token(42)

        assert token == "ghs_test"
        mock_client.post.assert_called_once()

    async def test_result_is_stored_in_cache(
        self, service: GitHubAppService, mocker: MockerFixture
    ):
        resp = _mock_response({"token": "ghs_cached", "expires_at": "2099-01-01T00:00:00Z"})
        mock_client = _mock_http_client(resp, method="post")
        mocker.patch("app.services.github_app.httpx.AsyncClient", return_value=mock_client)

        await service.get_installation_token(42)

        assert 42 in service._token_cache
        assert service._token_cache[42][0] == "ghs_cached"

    async def test_second_call_uses_cache_not_api(
        self, service: GitHubAppService, mocker: MockerFixture
    ):
        resp = _mock_response({"token": "ghs_once", "expires_at": "2099-01-01T00:00:00Z"})
        mock_client = _mock_http_client(resp, method="post")
        mocker.patch("app.services.github_app.httpx.AsyncClient", return_value=mock_client)

        service._token_cache.clear()
        await service.get_installation_token(10)
        await service.get_installation_token(10)

        assert mock_client.post.call_count == 1

    async def test_authorization_header_starts_with_bearer(
        self, service: GitHubAppService, mocker: MockerFixture
    ):
        resp = _mock_response({"token": "tok", "expires_at": "2099-01-01T00:00:00Z"})
        mock_client = _mock_http_client(resp, method="post")
        mocker.patch("app.services.github_app.httpx.AsyncClient", return_value=mock_client)

        service._token_cache.clear()
        await service.get_installation_token(5)

        _, call_kwargs = mock_client.post.call_args
        assert call_kwargs["headers"]["Authorization"].startswith("Bearer ")


# ---------------------------------------------------------------------------
# get_installation_for_repo
# ---------------------------------------------------------------------------


class TestGetInstallationForRepo:
    async def test_returns_installation_id(
        self, service: GitHubAppService, mocker: MockerFixture
    ):
        resp = _mock_response({"id": 9876})
        mock_client = _mock_http_client(resp, method="get")
        mocker.patch("app.services.github_app.httpx.AsyncClient", return_value=mock_client)

        result = await service.get_installation_for_repo("owner", "repo")

        assert result == 9876

    async def test_calls_correct_endpoint(
        self, service: GitHubAppService, mocker: MockerFixture
    ):
        resp = _mock_response({"id": 1})
        mock_client = _mock_http_client(resp, method="get")
        mocker.patch("app.services.github_app.httpx.AsyncClient", return_value=mock_client)

        await service.get_installation_for_repo("myorg", "myrepo")

        call_url = mock_client.get.call_args[0][0]
        assert "myorg" in call_url
        assert "myrepo" in call_url
