"""``PipelineContext`` — shared resources handed to every pipeline ``process`` fn.

Simplified from ``app_ref/services/worker/worker/context.py``: it carries a ``BlobClient``
(for pipelines that read/write large blobs) and the worker's ``AsyncSession``. The terminal
``Job`` row is still written *outside* ``process`` (by ``shared.worker.run_task``), but a
pipeline that persists its own domain rows — e.g. ``stack_analysis`` upserting ``TechStack``
(issue 018) — runs on the *same* session so its writes land in the same DB / transaction
boundary as the Job update. The trivial ``echo`` / ``ping`` probes ignore the context.
"""

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from shared.queue import BlobClient


@dataclass
class PipelineContext:
    """Resources available to a pipeline ``process(request, ctx)`` function."""

    blob: BlobClient | None = None
    session: AsyncSession | None = None
    # Optional shared GitHub client for a multi-step job (e.g. agentic_analysis). When set, sub-pipelines
    # reuse it instead of minting a token + creating their own — so a read-caching client can collapse the
    # repository tree / file fetches that every backbone step would otherwise repeat. ``None`` (standalone
    # invocation) keeps the previous per-pipeline behaviour. Typed ``Any`` because the concrete
    # ``GitHubGitClient`` lives in the ``service`` package, which ``shared`` must not import.
    github_client: Any = None
