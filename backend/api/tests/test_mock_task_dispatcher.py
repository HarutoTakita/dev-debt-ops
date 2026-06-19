"""Unit tests for the in-memory MockTaskDispatcher (dispatch / dedup / drain)."""

from app.services.mock_task_dispatcher import MockTaskDispatcher


async def test_dispatch_appends_tasks() -> None:
    dispatcher = MockTaskDispatcher()
    await dispatcher.dispatch("echo", {"jobId": "1", "message": "a"})
    await dispatcher.dispatch("ping", {"jobId": "2"})
    assert [t.pipeline for t in dispatcher.tasks] == ["echo", "ping"]


async def test_dedup_key_collapses_duplicates() -> None:
    dispatcher = MockTaskDispatcher()
    await dispatcher.dispatch("echo", {"jobId": "1"}, dedup_key="job-1")
    await dispatcher.dispatch("echo", {"jobId": "1"}, dedup_key="job-1")
    assert len(dispatcher.tasks) == 1


async def test_pop_all_drains_queue() -> None:
    dispatcher = MockTaskDispatcher()
    await dispatcher.dispatch("echo", {"jobId": "1"})
    popped = dispatcher.pop_all()
    assert len(popped) == 1
    assert dispatcher.tasks == []
