"""issue 069: shallow git checkout for Serena/LSP — success, failure, and graceful degradation.

The real ``git`` is exercised in e2e; here we mock the subprocess to verify the contract the
agentic pipeline relies on: a checked-out dir on success, ``None`` (with cleanup) on any failure so
the Twin Agent falls back to the REST repo tools.
"""

from pathlib import Path

import pytest

from service.services import repo_checkout


class _FakeProc:
    def __init__(self, returncode: int = 0) -> None:
        self.returncode = returncode
        self.killed = False

    async def communicate(self) -> tuple[bytes, bytes]:
        return (b"", b"")

    def kill(self) -> None:
        self.killed = True


async def test_shallow_clone_missing_inputs_returns_none() -> None:
    assert await repo_checkout.shallow_clone("o", "r", "main", "") is None


async def test_shallow_clone_success_returns_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_exec(*_args: object, **_kwargs: object) -> _FakeProc:
        return _FakeProc(returncode=0)

    monkeypatch.setattr(repo_checkout.asyncio, "create_subprocess_exec", _fake_exec)
    path = await repo_checkout.shallow_clone("acme", "rosetta", "main", "tok")
    assert path is not None
    assert Path(path).is_dir()  # noqa: ASYNC240 — deliberate sync FS assertion in a test
    repo_checkout._cleanup(path)  # caller owns cleanup


async def test_shallow_clone_failure_returns_none_and_cleans_up(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str] = {}

    async def _fake_exec(*_args: object, **_kwargs: object) -> _FakeProc:
        # Record the tmp dir (last positional arg of the git clone command) to assert cleanup.
        captured["dir"] = str(_args[-1])
        return _FakeProc(returncode=128)

    monkeypatch.setattr(repo_checkout.asyncio, "create_subprocess_exec", _fake_exec)
    assert await repo_checkout.shallow_clone("acme", "rosetta", "main", "tok") is None
    assert not Path(captured["dir"]).exists()  # noqa: ASYNC240 — deliberate sync FS assertion in a test


async def test_shallow_clone_git_missing_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _raise(*_args: object, **_kwargs: object) -> _FakeProc:
        raise FileNotFoundError("git not found")

    monkeypatch.setattr(repo_checkout.asyncio, "create_subprocess_exec", _raise)
    assert await repo_checkout.shallow_clone("acme", "rosetta", "main", "tok") is None
