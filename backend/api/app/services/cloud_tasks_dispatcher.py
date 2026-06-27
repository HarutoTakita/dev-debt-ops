"""``CloudTasksDispatcher`` — dispatches HTTP tasks to the service via Cloud Tasks.

``google-cloud-tasks`` is imported lazily so importing this module (and the mock-path
tests) never needs the client or credentials. Each task is an authenticated HTTP POST
to ``{SERVICE_TASKS_URL}/tasks/{pipeline}`` carrying an OIDC token, so the (internal)
service can verify the caller. ``dedup_key`` sets ``task.name`` for de-duplication.

Ported from ``app_ref`` ``azure_queue_client`` (send_message) + the issue-016 design.
"""

import json
from typing import Any

from app.core.config import settings


class CloudTasksDispatcher:
    """Cloud Tasks implementation of the ``TaskDispatcher`` Protocol."""

    def __init__(
        self,
        *,
        project: str,
        location: str,
        queue: str,
        service_url: str,
        invoker_sa: str,
        audience: str | None = None,
    ) -> None:
        self._project = project
        self._location = location
        self._queue = queue
        self._service_url = service_url.rstrip("/")
        self._invoker_sa = invoker_sa
        # OIDC audience is decoupled from the POST URL: the POST must hit the service's real
        # run.app URL, but the audience must be a stable value the service can verify (it can't
        # self-reference its own URL in Terraform). Falls back to service_url when unset.
        self._audience = (audience or self._service_url).rstrip("/")
        self._client = None  # lazily created tasks_v2.CloudTasksAsyncClient

    def _get_client(self):
        if self._client is None:
            from google.cloud import tasks_v2

            self._client = tasks_v2.CloudTasksAsyncClient()
        return self._client

    async def dispatch(self, pipeline: str, payload: dict[str, Any], *, dedup_key: str | None = None) -> None:
        """Create a Cloud Tasks HTTP task targeting ``service``'s ``/tasks/{pipeline}``."""
        from google.cloud import tasks_v2

        client = self._get_client()
        parent = client.queue_path(self._project, self._location, self._queue)
        url = f"{self._service_url}/tasks/{pipeline}"

        task: dict[str, Any] = {
            "http_request": {
                "http_method": tasks_v2.HttpMethod.POST,
                "url": url,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps(payload).encode(),
                "oidc_token": {
                    "service_account_email": self._invoker_sa,
                    "audience": self._audience,
                },
            }
        }
        if dedup_key is not None:
            task["name"] = f"{parent}/tasks/{dedup_key}"

        await client.create_task(request={"parent": parent, "task": task})

    @classmethod
    def from_settings(cls) -> "CloudTasksDispatcher":
        """Build a dispatcher from application settings (issue-017 injects the values)."""
        return cls(
            project=settings.GOOGLE_CLOUD_PROJECT,
            location=settings.GOOGLE_CLOUD_LOCATION,
            queue=settings.TASKS_QUEUE,
            service_url=settings.SERVICE_TASKS_URL,
            invoker_sa=settings.TASKS_INVOKER_SA,
            audience=settings.SERVICE_OIDC_AUDIENCE or None,
        )
