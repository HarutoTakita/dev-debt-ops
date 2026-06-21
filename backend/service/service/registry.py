"""Service pipeline registry.

The trivial ``echo`` / ``ping`` pipelines live in ``shared`` (so api's mock-worker can run
the same code). Heavy, service-only pipelines (``stack_analysis``, issue 018) are registered
here on top of the shared ones — they pull in ADK / Vertex AI / GitHub, which must not leak
into ``shared`` or ``api``. ``shared.worker.run_task`` resolves the active pipeline through
``service.registry.PIPELINES`` (the service ``/tasks/{pipeline}`` handler imports it).
"""

from service.pipelines import (
    agent_loop,
    code_debt_detection,
    feature_clustering,
    kc_analysis,
    knowledge_debt_detection,
    learning_plan_generation,
    quiz_generation,
    quiz_grading,
    repayment_pr_generation,
    stack_analysis,
)
from shared.enums import JobType
from shared.registry import PIPELINES as _SHARED_PIPELINES
from shared.schemas.agent_loop import AgentLoopRequest, AgentLoopResult
from shared.schemas.code_debt_detection import CodeDebtDetectionRequest, CodeDebtDetectionResult
from shared.schemas.feature_clustering import FeatureClusteringRequest, FeatureClusteringResult
from shared.schemas.kc_analysis import KcAnalysisRequest, KcAnalysisResult
from shared.schemas.knowledge_debt_detection import KnowledgeDebtDetectionRequest, KnowledgeDebtDetectionResult
from shared.schemas.learning_plan import LearningPlanGenerationRequest, LearningPlanGenerationResult
from shared.schemas.quiz import (
    QuizGenerationRequest,
    QuizGenerationResult,
    QuizGradingRequest,
    QuizGradingResult,
)
from shared.schemas.repayment_pr_generation import RepaymentPrGenerationRequest, RepaymentPrGenerationResult
from shared.schemas.stack_analysis import StackAnalysisRequest, StackAnalysisResult

PIPELINES = {
    **_SHARED_PIPELINES,
    JobType.STACK_ANALYSIS.value: (StackAnalysisRequest, StackAnalysisResult, stack_analysis.process),
    JobType.CODE_DEBT_DETECTION.value: (
        CodeDebtDetectionRequest,
        CodeDebtDetectionResult,
        code_debt_detection.process,
    ),
    JobType.KC_ANALYSIS.value: (KcAnalysisRequest, KcAnalysisResult, kc_analysis.process),
    JobType.KNOWLEDGE_DEBT_DETECTION.value: (
        KnowledgeDebtDetectionRequest,
        KnowledgeDebtDetectionResult,
        knowledge_debt_detection.process,
    ),
    JobType.REPAYMENT_PR_GENERATION.value: (
        RepaymentPrGenerationRequest,
        RepaymentPrGenerationResult,
        repayment_pr_generation.process,
    ),
    JobType.QUIZ_GENERATION.value: (QuizGenerationRequest, QuizGenerationResult, quiz_generation.process),
    JobType.QUIZ_GRADING.value: (QuizGradingRequest, QuizGradingResult, quiz_grading.process),
    JobType.LEARNING_PLAN_GENERATION.value: (
        LearningPlanGenerationRequest,
        LearningPlanGenerationResult,
        learning_plan_generation.process,
    ),
    JobType.CODE_DEBT_LOOP.value: (AgentLoopRequest, AgentLoopResult, agent_loop.process),
    JobType.KNOWLEDGE_DEBT_LOOP.value: (AgentLoopRequest, AgentLoopResult, agent_loop.process),
    JobType.FEATURE_CLUSTERING.value: (
        FeatureClusteringRequest,
        FeatureClusteringResult,
        feature_clustering.process,
    ),
}
