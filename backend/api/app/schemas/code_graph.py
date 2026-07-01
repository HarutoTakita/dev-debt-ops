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


class FileFunctionGraphOut(BaseModel):
    """One file's internal function call graph (Level-3, issue 240) — lazily fetched on file click.

    ``nodes`` = function names in the file; ``edges`` = intra-file calls. Functions carry no KC, so
    this is a pure structure view. ``observed=false`` when no graph is persisted for the project.
    """

    observed: bool
    nodes: list[dict] = []
    edges: list[dict] = []


class FeatureFunctionGraphOut(BaseModel):
    """A feature's function-level graph (Level-2, issue 282) — lazily fetched on feature click.

    Files become cluster "hub" nodes, functions their children (``CONTAINS`` edges), connected by
    function ``CALLS`` (intra- and cross-file, within the feature's files). This gives the dense,
    connected structure of the CodeGraphContext view and guarantees no function floats disconnected.

    - ``nodes``: ``{id, label, file, kind}`` where ``kind`` is ``"file"`` (hub) or ``"function"``;
      ``id`` is composite (``"file::<path>"`` / ``"<file>::<name>"``) to avoid same-name collisions.
    - ``edges``: ``{source, target, type}`` where ``type`` is ``"contains"`` or ``"calls"``.
    - ``truncated``: ``true`` when the node cap dropped some functions (no silent truncation).
    ``observed=false`` when no graph / feature-clustering run is available.
    """

    observed: bool
    nodes: list[dict] = []
    edges: list[dict] = []
    truncated: bool = False
