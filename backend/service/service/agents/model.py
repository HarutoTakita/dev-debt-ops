"""Vertex AI model resolution for ADK agents (issue 069 Phase 0)."""

from service import config


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
