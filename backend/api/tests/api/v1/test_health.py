from httpx import AsyncClient


async def test_health_returns_ok(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    # RequestContextMiddleware echoes a correlation id on every response (issue 302).
    assert response.headers.get("x-request-id")


async def test_readiness_reports_db_and_memory(client: AsyncClient) -> None:
    """Readiness probe: DB reachable → 200 with per-check details (issue 301)."""
    response = await client.get("/api/v1/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"]
    assert body["uptime_seconds"] >= 0
    # database check ran a real SELECT 1 and reported latency.
    assert body["database"]["status"] == "ok"
    assert isinstance(body["database"]["latency_ms"], (int, float))
    # memory check reports RSS (or 'unknown' if /proc is unavailable).
    assert body["memory"]["status"] in {"ok", "unknown"}
