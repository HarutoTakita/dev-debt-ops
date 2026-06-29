"""Vertex AI model resolution for ADK agents (issue 069 Phase 0)."""

from functools import cached_property
from typing import Any

from google.adk.models import Gemini
from google.genai import Client, types

from service import config

# 429/5xx に対する自動リトライ（指数バックオフ）。バックボーン側 (gemini_stack_service._generate) と
# 同等の設定。タイムアウトと併用することで「応答が来ない無限待ち」も「瞬間的なクォータ超過」も両方を吸収。
_AGENT_RETRY_STATUS = [429, 500, 503]
_AGENT_RETRY_ATTEMPTS = 6


def vertex_model_name() -> str:
    """Return the Vertex AI full resource path for the configured Gemini model.

    With a project configured, returns ``projects/.../publishers/google/models/<model>`` so
    ADK's Gemini client authenticates via Vertex AI + ADC (no API key). Falls back to the bare
    model id when no project is set (local/dev). Generalises ``stack_analysis._vertex_model_name``
    so every agent resolves its model the same way.
    """
    project = config.google_cloud_project()
    if project:
        return (
            f"projects/{project}"
            f"/locations/{config.google_cloud_location()}"
            f"/publishers/google/models/{config.gemini_model()}"
        )
    return config.gemini_model()


class _BoundedGemini(Gemini):
    """ADK ``Gemini`` model with a client-side timeout + 429/5xx retry.

    ADK builds its own ``google.genai.Client`` and does NOT expose a request ``timeout`` (only
    ``retry_options``). Without a timeout, a stalled Vertex response blocks the agent forever and
    the Job sticks in ``PROCESSING`` (the same failure the backbone hit before its own client got a
    timeout). ADK's docstring says to subclass and override ``api_client`` for options it doesn't
    expose; this mirrors ADK's own ``api_client`` (so Vertex/ADC resolution is unchanged) and adds
    ``timeout``. ``retry_options`` is set via the field on the instance (``build_agent_model``).
    """

    @cached_property
    def api_client(self) -> Client:
        base_url, api_version = self._base_url_and_api_version
        http_kwargs: dict[str, Any] = {
            "headers": self._tracking_headers(),
            "retry_options": self.retry_options,
            "base_url": base_url,
            "timeout": config.gemini_timeout_ms(),
        }
        if api_version:
            http_kwargs["api_version"] = api_version
        client_kwargs: dict[str, Any] = {"http_options": types.HttpOptions(**http_kwargs)}
        if self.model.startswith("projects/"):
            client_kwargs["vertexai"] = True
        return Client(**client_kwargs)


def build_agent_model() -> _BoundedGemini:
    """Return the ADK model every Twin Agent ``LlmAgent`` should use.

    Wraps ``vertex_model_name()`` in a ``Gemini`` whose genai client has a bounded request timeout
    (``config.gemini_timeout_ms()``) and exponential-backoff retry on 429/5xx — so a single stalled
    or rate-limited model call can no longer hang the whole agentic run.
    """
    return _BoundedGemini(
        model=vertex_model_name(),
        retry_options=types.HttpRetryOptions(
            attempts=_AGENT_RETRY_ATTEMPTS,
            initial_delay=2.0,
            max_delay=32.0,
            exp_base=2.0,
            http_status_codes=_AGENT_RETRY_STATUS,
        ),
    )
