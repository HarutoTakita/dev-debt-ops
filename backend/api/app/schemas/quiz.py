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
    flagged_question_ids: list[str] = []  # このユーザーがフラグを付けた設問 id（#6）
    retest_mode: str | None = None  # None=通常 / "flagged" / "wrong"（#6 再テストで生成された場合）


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
    # 再受験（retest）か。初回受験は前回値が無く差分が「クイズ結果 vs 著作推定」で紛らわしいため、
    # フロントは再受験（2回目以降）のときだけ KC 差分を表示する。
    is_retake: bool = False


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


class FlagQuestionIn(BaseModel):
    """Body for ``PUT .../quizzes/{id}/questions/{question_id}/flag`` (#6)."""

    flagged: bool


class RetestIn(BaseModel):
    """Body for ``POST .../quizzes/{id}/retest`` (#6). flagged=フラグ設問のみ / wrong=全回誤答のみ."""

    mode: str  # "flagged" | "wrong"


class RetestOut(BaseModel):
    """Result of creating a filtered re-test session (#6)."""

    session_id: str
    question_count: int


class BaselineQuizzesOut(BaseModel):
    """Summary for ``POST .../baseline-quizzes`` (issue 054)."""

    created: int
    job_ids: list[str]
