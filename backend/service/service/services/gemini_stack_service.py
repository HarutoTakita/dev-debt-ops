"""Gemini-powered repository tech-stack analyser (google-genai SDK, Vertex AI).

Moved from api's ``app.services.gemini_stack_service`` (issue 018): the heavy Vertex AI
call now runs inside the ``service`` container. Project / region come from ``service.config``
(env-based) instead of api's pydantic ``Settings``; auth is ADC only (no API key), and the
service runtime SA must hold ``roles/aiplatform.user``.
"""

import json

import google.auth
import google.auth.exceptions
from google import genai
from google.genai import types

from service import config

_PROMPT_TEMPLATE = """\
You are analysing a software repository. Based on the configuration files below, \
identify the technologies used.

{file_section}

Return ONLY a valid JSON object — no markdown, no explanation — matching this exact schema:
{{
  "languages": [{{"name": "...", "confidence": "high|medium|low"}}],
  "categories": {{
    "frameworks":  [{{"name": "...", "confidence": "high|medium|low"}}],
    "databases":   [{{"name": "...", "confidence": "high|medium|low"}}],
    "auth":        [{{"name": "...", "confidence": "high|medium|low"}}],
    "container":   [{{"name": "...", "confidence": "high|medium|low"}}],
    "infra":       [{{"name": "...", "confidence": "high|medium|low"}}],
    "cicd":        [{{"name": "...", "confidence": "high|medium|low"}}],
    "monitoring":  [{{"name": "...", "confidence": "high|medium|low"}}],
    "testing":     [{{"name": "...", "confidence": "high|medium|low"}}],
    "other":       [{{"name": "...", "confidence": "high|medium|low"}}]
  }}
}}

Rules:
- confidence "high"   = clearly evident from file contents
- confidence "medium" = likely based on indirect evidence
- confidence "low"    = possible but uncertain
- Use an empty array [] for categories with no detected technologies.
- Do NOT invent technologies not evidenced by the files.
"""

_MAX_FILE_CHARS = 5_000


def _build_file_section(file_map: dict[str, str]) -> str:
    parts: list[str] = []
    for name, content in file_map.items():
        truncated = content[:_MAX_FILE_CHARS]
        if len(content) > _MAX_FILE_CHARS:
            truncated += "\n... (truncated)"
        parts.append(f"=== {name} ===\n{truncated}")
    return "\n\n".join(parts)


def _empty_result() -> dict:
    return {
        "languages": [],
        "categories": {
            "frameworks": [],
            "databases": [],
            "auth": [],
            "container": [],
            "infra": [],
            "cicd": [],
            "monitoring": [],
            "testing": [],
            "other": [],
        },
    }


def _build_client() -> genai.Client:
    """Return a Gemini client using Vertex AI + ADC, or raise ValueError."""
    project = config.google_cloud_project()
    location = config.google_cloud_location()

    if not project:
        raise ValueError("GOOGLE_CLOUD_PROJECT is not configured.")

    try:
        credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    except google.auth.exceptions.DefaultCredentialsError as e:
        raise ValueError(
            "Google credentials not configured. Set GOOGLE_APPLICATION_CREDENTIALS to your service account JSON path."
        ) from e

    return genai.Client(
        vertexai=True,
        project=project,
        location=location,
        credentials=credentials,
    )


async def analyze_tech_stack(file_map: dict[str, str]) -> dict:
    """Return a tech-stack classification dict produced by Gemini via Vertex AI.

    Raises ValueError if GOOGLE_CLOUD_PROJECT or credentials are not configured.
    """
    client = _build_client()

    if not file_map:
        return _empty_result()

    prompt = _PROMPT_TEMPLATE.format(file_section=_build_file_section(file_map))

    response = await client.aio.models.generate_content(
        model=config.gemini_model(),
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.1,
        ),
    )

    try:
        return json.loads(response.text)  # ty: ignore[invalid-argument-type]
    except (json.JSONDecodeError, AttributeError):
        return _empty_result()
