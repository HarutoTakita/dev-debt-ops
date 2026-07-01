"""estimate_ai_generation — per-content memoisation (Phase 0 dedupe, issue 261)."""

import pytest

from service.services import gemini_stack_service as g


class _Resp:
    text = '{"a.py": 0.9, "b.py": 0.8}'


async def test_estimate_ai_generation_memoises_by_content(monkeypatch: pytest.MonkeyPatch) -> None:
    """Same file content is estimated once; a fully-cached call makes no Gemini request."""
    calls = {"n": 0}

    async def fake_generate(_client: object, *, model: str, contents: str, config: object) -> _Resp:
        calls["n"] += 1
        return _Resp()

    monkeypatch.setattr(g, "_build_client", lambda: object())
    monkeypatch.setattr(g, "_generate", fake_generate)
    g._AI_GEN_CACHE.clear()

    r1 = await g.estimate_ai_generation({"a.py": "AAA", "b.py": "BBB"})
    assert r1 == {"a.py": 0.9, "b.py": 0.8}
    assert calls["n"] == 1

    # Same contents again (e.g. the knowledge-debt step over files code-debt already estimated) → no call.
    r2 = await g.estimate_ai_generation({"a.py": "AAA", "b.py": "BBB"})
    assert r2 == {"a.py": 0.9, "b.py": 0.8}
    assert calls["n"] == 1  # served entirely from cache

    # A new file mixed with a cached one → one call, only for the uncached file.
    await g.estimate_ai_generation({"a.py": "AAA", "c.py": "CCC"})
    assert calls["n"] == 2

    # Same path but different content is a cache miss (keyed by content, not path).
    await g.estimate_ai_generation({"a.py": "DIFFERENT"})
    assert calls["n"] == 3


async def test_estimate_ai_generation_empty_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_generate(*_a: object, **_k: object) -> _Resp:  # pragma: no cover - must not run
        raise AssertionError("should not call Gemini for empty input")

    monkeypatch.setattr(g, "_generate", fake_generate)
    assert await g.estimate_ai_generation({}) == {}
