"""Unit tests for the ADK agent foundation (issue 069 Phase 0).

Pure-logic tests for model resolution, event→trace adaptation, run budget + callback factories,
and the deterministic code-metric tool wrappers. No DB / network needed.
"""

import pytest

from service.agents import (
    BudgetExceeded,
    RunBudget,
    event_to_trace,
    make_before_model_callback,
    make_before_tool_callback,
    summarize_args,
    vertex_model_name,
)
from service.agents import tools as agent_tools
from service.services import code_analysis

# --- model -----------------------------------------------------------------


def test_vertex_model_name_uses_vertex_path_when_project_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """With a project, the model resolves to a Vertex AI full resource path (ADC auth)."""
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "proj-1")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "asia-northeast1")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")
    assert vertex_model_name() == (
        "projects/proj-1/locations/asia-northeast1/publishers/google/models/gemini-2.5-flash"
    )


def test_vertex_model_name_falls_back_to_bare_id_without_project(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without a project, the bare model id is used."""
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")
    assert vertex_model_name() == "gemini-2.5-flash"


# --- trace -----------------------------------------------------------------


def test_summarize_args_compacts_large_values() -> None:
    """Long strings and containers are summarised by size, scalars kept verbatim."""
    summary = summarize_args({"big": "x" * 100, "d": {"a": 1}, "lst": [1, 2, 3], "n": 5})
    assert "big=<100chars>" in summary
    assert "d=<dict:1keys>" in summary
    assert "lst=<list:3items>" in summary
    assert "n=5" in summary


def test_summarize_args_handles_none() -> None:
    """``None`` args summarise to an empty string."""
    assert summarize_args(None) == ""


class _FakeFunctionCall:
    def __init__(self, name: str, args: dict | None) -> None:
        self.name = name
        self.args = args


class _FakeFunctionResponse:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakePart:
    def __init__(self, *, function_call: object = None, function_response: object = None, text: str | None = None):
        self.function_call = function_call
        self.function_response = function_response
        self.text = text


class _FakeContent:
    def __init__(self, parts: list[object]) -> None:
        self.parts = parts


class _FakeEvent:
    def __init__(self, parts: list[object]) -> None:
        self.content = _FakeContent(parts)


def test_event_to_trace_renders_calls_responses_and_text() -> None:
    """Tool calls, responses and free text map to [call]/[done]/[summary] lines."""
    event = _FakeEvent(
        [
            _FakePart(function_call=_FakeFunctionCall("list_source_files", {"paths": [1, 2]})),
            _FakePart(function_response=_FakeFunctionResponse("list_source_files")),
            _FakePart(text="found 3 hotspots"),
        ]
    )
    assert event_to_trace(event) == [
        "[call] list_source_files(paths=<list:2items>)",
        "[done] list_source_files",
        "[summary] found 3 hotspots",
    ]


def test_event_to_trace_empty_when_no_parts() -> None:
    """An event without content/parts yields no trace lines."""
    assert event_to_trace(object()) == []


# --- budget ----------------------------------------------------------------


def test_run_budget_tool_cap_raises_when_exceeded() -> None:
    """Charging past the tool-call cap raises BudgetExceeded; remaining decrements to zero."""
    budget = RunBudget(max_tool_calls=2)
    budget.charge_tool_call()
    assert budget.remaining_tool_calls() == 1
    budget.charge_tool_call()
    assert budget.remaining_tool_calls() == 0
    with pytest.raises(BudgetExceeded, match="tool-call budget exceeded"):
        budget.charge_tool_call()


def test_run_budget_model_and_file_caps() -> None:
    """Model-call and file-read caps raise BudgetExceeded when passed."""
    budget = RunBudget(max_model_calls=1, max_files=5)
    budget.charge_model_call()
    with pytest.raises(BudgetExceeded, match="model-call budget exceeded"):
        budget.charge_model_call()
    with pytest.raises(BudgetExceeded, match="file-read budget exceeded"):
        budget.charge_files(6)


# --- hooks -----------------------------------------------------------------


def test_before_tool_callback_short_circuits_when_exhausted() -> None:
    """Under budget returns None (run the tool); over budget returns a short-circuit dict."""
    budget = RunBudget(max_tool_calls=1)
    callback = make_before_tool_callback(budget)
    assert callback("tool", {"a": 1}, "ctx") is None
    result = callback("tool", {"a": 1}, "ctx")
    assert result is not None
    assert result["budget_exceeded"] is True


def test_before_model_callback_raises_when_exhausted() -> None:
    """The model callback charges the budget and raises once the cap is passed."""
    budget = RunBudget(max_model_calls=1)
    callback = make_before_model_callback(budget)
    assert callback(object(), object()) is None
    with pytest.raises(BudgetExceeded, match="model-call budget exceeded"):
        callback(object(), object())


def test_after_tool_callback_passes_small_results_through() -> None:
    """A small tool result is left untouched (returns None → ADK keeps the original)."""
    from service.agents.hooks import make_after_tool_callback

    callback = make_after_tool_callback()
    assert callback(tool_response={"ok": True, "items": [1, 2, 3]}) is None


def test_after_tool_callback_truncates_large_results() -> None:
    """An oversized tool result is replaced with a bounded stand-in (issue 260 follow-up)."""
    from service.agents.hooks import _MAX_TOOL_RESULT_CHARS, make_after_tool_callback

    callback = make_after_tool_callback()
    huge = {"vulnerabilities": ["x" * 50 for _ in range(2000)]}  # serialises well past the cap
    out = callback(tool_response=huge)
    assert out is not None
    assert out["truncated"] is True
    assert len(out["result"]) <= _MAX_TOOL_RESULT_CHARS + 100  # cap + short suffix
    assert out["original_chars"] > _MAX_TOOL_RESULT_CHARS


def test_after_tool_callback_ignores_missing_or_unserializable() -> None:
    """No tool_response → None; a non-JSON-serialisable response is left to ADK (None)."""
    from service.agents.hooks import make_after_tool_callback

    callback = make_after_tool_callback()
    assert callback() is None
    assert callback(tool_response=object()) is None


# --- tools (delegate to code_analysis) -------------------------------------


def test_list_source_files_delegates_to_code_analysis() -> None:
    """The tool filters via code_analysis.is_source_file (delegation, not its own rules)."""
    paths = ["app/main.py", "node_modules/x/index.js", "README.md", "infra/main.tf"]
    assert agent_tools.list_source_files(paths) == [p for p in paths if code_analysis.is_source_file(p)]


def test_duplication_findings_shape() -> None:
    """Each duplication finding carries file_path / duplicate_ratio / score."""
    files = {"a.py": "x = 1\ny = 2\n", "b.py": "x = 1\ny = 2\n"}
    for finding in agent_tools.duplication_findings(files):
        assert {"file_path", "duplicate_ratio", "score"} <= set(finding)


def test_dead_file_findings_delegates_and_sorts() -> None:
    """Dead-file findings equal the sorted code_analysis result."""
    files = {"a.py": "import b\n", "b.py": "value = 1\n"}
    assert agent_tools.dead_file_findings(files) == sorted(code_analysis.find_dead_files(files))
