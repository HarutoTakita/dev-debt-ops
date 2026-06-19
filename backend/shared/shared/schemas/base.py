"""Shared pydantic base models used by api / service pipeline payloads."""

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class SharedBaseModel(BaseModel):
    """Base model with camelCase aliasing for queue / JSON payloads.

    Fields are declared in snake_case but (de)serialize as camelCase, while still
    accepting snake_case input (``populate_by_name``).
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class PipelineError(SharedBaseModel):
    """Structured error reported by a pipeline run."""

    code: str
    message: str
