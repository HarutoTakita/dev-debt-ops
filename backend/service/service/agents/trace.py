"""Adapt ADK ``Runner`` events into ``agent_trace`` lines (issue 069 Phase 0).

Generalises the inline event loop in ``stack_analysis.run_stack_analysis`` so every agent can
turn its tool calls / responses / final text into the same compact trace recorded on
``Job.result_data``. Events are accepted duck-typed (``object``) so this stays decoupled from a
specific ADK version and is trivially unit-testable with fakes.
"""


def summarize_args(args: dict | None) -> str:
    """Return a compact one-line summary of tool-call arguments for trace logging.

    Long strings and containers are summarised by size so the trace never embeds large payloads.
    """
    parts: list[str] = []
    for key, value in (args or {}).items():
        if isinstance(value, str) and len(value) > 80:
            parts.append(f"{key}=<{len(value)}chars>")
        elif isinstance(value, dict):
            parts.append(f"{key}=<dict:{len(value)}keys>")
        elif isinstance(value, list):
            parts.append(f"{key}=<list:{len(value)}items>")
        else:
            parts.append(f"{key}={value!r}")
    return ", ".join(parts)


def event_to_trace(event: object) -> list[str]:
    """Convert one ADK event into zero or more ``agent_trace`` lines.

    Emits ``[call] name(args)`` for tool calls, ``[done] name`` for tool responses, and
    ``[summary] text`` for free-text parts (truncated). Parts without recognised content are
    skipped. ``event`` is read duck-typed (``event.content.parts``; each part's
    ``function_call`` / ``function_response`` / ``text``).
    """
    content = getattr(event, "content", None)
    parts = getattr(content, "parts", None) if content is not None else None
    if not parts:
        return []

    lines: list[str] = []
    for part in parts:
        function_call = getattr(part, "function_call", None)
        function_response = getattr(part, "function_response", None)
        text = getattr(part, "text", None)
        if function_call:
            name = getattr(function_call, "name", "?")
            args = getattr(function_call, "args", None)
            lines.append(f"[call] {name}({summarize_args(args)})")
        elif function_response:
            lines.append(f"[done] {getattr(function_response, 'name', '?')}")
        elif text:
            lines.append(f"[summary] {str(text)[:500]}")
    return lines
