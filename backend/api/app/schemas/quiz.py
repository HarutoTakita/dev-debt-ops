"""Quiz delivery schemas (issue 034) — snake_case, matching ``schemas.ts`` quiz contract.

Plain ``BaseModel`` so field names stay snake_case. ``questions`` are passed through as stored dicts
(already in ``quizQuestionSchema`` shape, answer key stripped). ``file`` nests ``{path, repo_full_name}``.
"""

from datetime import datetime

from pydantic import BaseModel


class FileRefOut(BaseModel):
    """The file a quiz targets."""

    path: str
    repo_full_name: str


class QuizAnswerOut(BaseModel):
    """One saved answer (``quizAnswerSchema``)."""

    question_id: str
    value: str
    saved_at: datetime


class QuizSessionOut(BaseModel):
    """A quiz session (``quizSessionSchema``); ``questions`` exclude the answer key."""

    id: str
    developer_id: str
    file: FileRefOut
    questions: list[dict]
    answers: list[QuizAnswerOut]
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    score: float | None


class QuizReviewItemOut(BaseModel):
    """One question's post-grade review row (#4 誤答チェック). Correct answer is exposed post-completion."""

    question_id: str
    prompt: str
    your_answer: str  # 選んだ選択肢ラベル（複数は「, 」区切り）。未回答は空文字。
    correct_answer: str  # 正答ラベル（複数は「, 」区切り）。
    is_correct: bool
    flagged: bool = False  # このユーザーがこの設問にフラグを付けているか（#6）


class QuizResultOut(BaseModel):
    """A graded result (``quizResultSchema``)."""

    session_id: str
    understood: list[dict]
    gap_concepts: list[dict]
    kc_before: float
    kc_after: float
    learning_plan_id: str | None
    review: list[QuizReviewItemOut] = []  # 全設問の正誤レビュー（#4）


class QuizListItemOut(BaseModel):
    """One row of the available-quiz list (``quizListItemSchema``)."""

    session_id: str
    file_path: str
    repo_full_name: str
    reason: str
    question_count: int
    estimated_minutes: int


class QuizListOut(BaseModel):
    """``quizListSchema``."""

    quizzes: list[QuizListItemOut]


class GenerateQuizIn(BaseModel):
    """Body for ``POST .../quizzes/generate``."""

    file_path: str


class SaveAnswerIn(BaseModel):
    """Body for ``PATCH .../quizzes/{id}/answers``."""

    question_id: str
    value: str


class BaselineQuizzesOut(BaseModel):
    """Summary for ``POST .../baseline-quizzes`` (issue 054)."""

    created: int
    job_ids: list[str]
