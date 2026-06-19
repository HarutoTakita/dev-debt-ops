"""Service pipeline registry.

The trivial ``echo`` / ``ping`` pipelines live in ``shared`` (so api's mock-worker can run
the same code). Heavy, service-only pipelines (``stack_analysis``, issue 018) are registered
here on top of the shared ones — they pull in ADK / Vertex AI / GitHub, which must not leak
into ``shared`` or ``api``. ``shared.worker.run_task`` resolves the active pipeline through
``service.registry.PIPELINES`` (the service ``/tasks/{pipeline}`` handler imports it).
"""

from service.pipelines import code_debt_detection, stack_analysis
from shared.enums import JobType
from shared.registry import PIPELINES as _SHARED_PIPELINES
from shared.schemas.code_debt_detection import CodeDebtDetectionRequest, CodeDebtDetectionResult
from shared.schemas.stack_analysis import StackAnalysisRequest, StackAnalysisResult

PIPELINES = {
    **_SHARED_PIPELINES,
    JobType.STACK_ANALYSIS.value: (StackAnalysisRequest, StackAnalysisResult, stack_analysis.process),
    JobType.CODE_DEBT_DETECTION.value: (
        CodeDebtDetectionRequest,
        CodeDebtDetectionResult,
        code_debt_detection.process,
    ),
}
