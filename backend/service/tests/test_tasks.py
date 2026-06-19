"""Smoke test for the /tasks/{pipeline} stub (202 Accepted, no processing yet)."""

from httpx import AsyncClient


async def test_tasks_stub_accepts_and_returns_202(client: AsyncClient) -> None:
    """POST /tasks/{pipeline} accepts a body and returns 202 Accepted (stub)."""
    resp = await client.post("/tasks/echo", json={"jobId": "abc", "hello": "world"})
    assert resp.status_code == 202
    body = resp.json()
    assert body["accepted"] is True
    assert body["pipeline"] == "echo"
