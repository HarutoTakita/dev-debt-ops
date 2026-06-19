"""``PipelineContext`` — shared resources handed to every pipeline ``process`` fn.

Simplified from ``app_ref/services/worker/worker/context.py``: it carries only the
``BlobClient`` (for pipelines that read/write large blobs). DB writes happen *outside*
``process`` (the service handler / mock-worker persists the ``Job`` row), so the context
holds no DB session and no result publisher.
"""

from dataclasses import dataclass

from shared.queue import BlobClient


@dataclass
class PipelineContext:
    """Resources available to a pipeline ``process(request, ctx)`` function."""

    blob: BlobClient | None = None
