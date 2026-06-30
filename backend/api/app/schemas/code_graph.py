"""Code-graph delivery schema (issue 235) — the persisted CodeGraphContext snapshot for a project.

``GET .../code-graph`` returns ``observed=false`` (empty) until an agentic analysis has built and
persisted a graph. A future frontend renders ``nodes`` / ``edges`` as a node-link map.
"""

from datetime import datetime

from pydantic import BaseModel


class CodeGraphOut(BaseModel):
    """File↔file coupling snapshot (cross-file function calls aggregated to files, issue 238).

    Consumed by the understanding map's Level-2 file subgraph; paths are repo-relative (match
    ``file_kc``). ``observed=false`` until an analysis has built and persisted a graph.
    """

    observed: bool
    computed_at: datetime | None = None
    file_edges: list[dict] = []
