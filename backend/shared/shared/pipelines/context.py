"""``PipelineContext`` — shared resources handed to every pipeline ``process`` fn.

Simplified from ``app_ref/services/worker/worker/context.py``: it carries a ``BlobClient``
(for pipelines that read/write large blobs) and the worker's ``AsyncSession``. The terminal
``Job`` row is still written *outside* ``process`` (by ``shared.worker.run_task``), but a
pipeline that persists its own domain rows — e.g. ``stack_analysis`` upserting ``TechStack``
(issue 018) — runs on the *same* session so its writes land in the same DB / transaction
boundary as the Job update. The trivial ``echo`` / ``ping`` probes ignore the context.
"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from shared.queue import BlobClient


@dataclass
class PipelineContext:
    """Resources available to a pipeline ``process(request, ctx)`` function."""

    blob: BlobClient | None = None
    session: AsyncSession | None = None
