"""Code-graph delivery schema (issue 235) — the persisted CodeGraphContext snapshot for a project.

``GET .../code-graph`` returns ``observed=false`` (empty) until an agentic analysis has built and
persisted a graph. A future frontend renders ``nodes`` / ``edges`` as a node-link map.
"""

from datetime import datetime

from pydantic import BaseModel


class CodeGraphOut(BaseModel):
    """Node-link snapshot of the repository's code graph (function call graph)."""

    observed: bool
    computed_at: datetime | None = None
    nodes: list[dict] = []
    edges: list[dict] = []
