"""Shared ORM models, re-exported for ``from shared.models import Job, TechStack``."""

from shared.models.job import Job
from shared.models.tech_stack import TechStack

__all__ = ["Job", "TechStack"]
