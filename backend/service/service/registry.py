"""Service pipeline registry.

The trivial ``echo`` / ``ping`` pipelines live in ``shared`` (so api's mock-worker can
run the same code). The service exposes them here and is where heavy, service-only
pipelines (e.g. ``stack_analysis``, issue-018) get registered alongside the shared ones.
"""

from shared.registry import PIPELINES as PIPELINES

# issue-018 will extend with service-local heavy pipelines, e.g.:
#   from service.pipelines import stack_analysis
#   PIPELINES = {**PIPELINES, JobType.STACK_ANALYSIS.value: (..., ..., stack_analysis.process)}
