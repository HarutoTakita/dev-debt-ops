import type { QuizList, QuizResult, QuizSession } from "$lib/api/schemas";

// クイズ返済体験のモック。題材は仕様書 §6.5 のナラティブ例（UserService.ts）。
// 機能本体（実採点・実 API）は未実装で、UI の形を見せる目的で使う。

const USER_SERVICE_SNIPPET = `async getUserById(id: string): Promise<User> {
  // 2 層キャッシュ（メモリ + Redis）。理由は ADR-0012 にある
  const cached = this.mem.get(id) ?? (await this.redis.get(id));
  if (cached) return cached;
  return this.repo.findById(id);
}`;

const TOKEN_ROTATION_SNIPPET = `export function rotate(token: RefreshToken): RefreshToken {
  // 再利用検出: 古いトークンは失効させ、新規を発行する
  if (token.used) throw new ReuseDetectedError();
  return issue({ ...token, used: false, jti: nextJti() });
}`;

const SESSIONS: Record<string, QuizSession> = {
  "quiz-user-service": {
    id: "quiz-user-service",
    developer_id: "you",
    file: { path: "src/services/user-service.ts", repo_full_name: "demo/app" },
    status: "not_started",
    started_at: null,
    completed_at: null,
    score: null,
    answers: [],
    questions: [
      {
        id: "q1",
        kind: "multiple_choice",
        difficulty: "L1",
        prompt: "UserService の主な責務を最もよく表すものは？",
        code_snippet: null,
        choices: [
          { id: "a", label: "ユーザーの取得・更新と監査連携" },
          { id: "b", label: "HTTP ルーティング" },
          { id: "c", label: "DB マイグレーション" },
        ],
      },
      {
        id: "q2",
        kind: "free_text",
        difficulty: "L2",
        prompt: "getUserById(123) を呼んだとき、内部でどのような処理が順に起こりますか？",
        code_snippet: { language: "ts", path: "src/services/user-service.ts", content: USER_SERVICE_SNIPPET },
      },
      {
        id: "q3",
        kind: "multiple_choice",
        difficulty: "L3",
        prompt: "なぜ getUserById は 2 層キャッシュ（メモリ + Redis）なのですか？",
        code_snippet: { language: "ts", path: "src/services/user-service.ts", content: USER_SERVICE_SNIPPET },
        choices: [
          { id: "a", label: "速度のためだけ" },
          { id: "b", label: "ADR-0012 の DB 死活独立性ポリシーに基づく冗長化" },
          { id: "c", label: "歴史的な偶然" },
        ],
      },
      {
        id: "q4",
        kind: "free_text",
        difficulty: "L4",
        prompt: "isAdmin チェックを外すと、システム全体にどのような影響が出ますか？",
        code_snippet: null,
      },
      {
        id: "q5",
        kind: "multiple_choice",
        difficulty: "L5",
        prompt: "UserService.update を呼ぶとき、AuditLogService との連携で気をつけることは？",
        code_snippet: null,
        choices: [
          { id: "a", label: "監査ログは同一トランザクションで書く" },
          { id: "b", label: "監査ログは不要" },
          { id: "c", label: "ログは後で手動で書く" },
        ],
      },
    ],
  },
  "quiz-token-rotation": {
    id: "quiz-token-rotation",
    developer_id: "you",
    file: { path: "src/auth/token-rotation.ts", repo_full_name: "demo/app" },
    status: "not_started",
    started_at: null,
    completed_at: null,
    score: null,
    answers: [],
    questions: [
      {
        id: "q1",
        kind: "multiple_choice",
        difficulty: "L1",
        prompt: "token-rotation.ts の目的は？",
        code_snippet: null,
        choices: [
          { id: "a", label: "リフレッシュトークンのローテーションと再利用検出" },
          { id: "b", label: "パスワードハッシュ化" },
          { id: "c", label: "CORS 設定" },
        ],
      },
      {
        id: "q2",
        kind: "free_text",
        difficulty: "L2",
        prompt: "rotate() を呼ぶと、トークンはどう変化しますか？",
        code_snippet: { language: "ts", path: "src/auth/token-rotation.ts", content: TOKEN_ROTATION_SNIPPET },
      },
      {
        id: "q3",
        kind: "multiple_choice",
        difficulty: "L3",
        prompt: "再利用検出（ReuseDetectedError）が必要な理由は？",
        code_snippet: { language: "ts", path: "src/auth/token-rotation.ts", content: TOKEN_ROTATION_SNIPPET },
        choices: [
          { id: "a", label: "盗まれたトークンの再使用を検出して全セッションを失効させるため" },
          { id: "b", label: "パフォーマンス向上のため" },
          { id: "c", label: "ログ削減のため" },
        ],
      },
      {
        id: "q4",
        kind: "free_text",
        difficulty: "L4",
        prompt: "再利用検出を外すと、どのような攻撃が成立しますか？",
        code_snippet: null,
      },
      {
        id: "q5",
        kind: "free_text",
        difficulty: "L5",
        prompt: "rotate() と SessionStore・AuditLog の連携で気をつける不変条件は？",
        code_snippet: null,
      },
    ],
  },
};

const RESULT: QuizResult = {
  session_id: "quiz-user-service",
  understood: [
    { id: "c1", label: "トークンローテーションの基本" },
    { id: "c2", label: "JWT 有効期限の意図" },
    { id: "c3", label: "2 層キャッシュの速度面の利点" },
  ],
  gap_concepts: [
    { id: "g1", label: "再利用検出の不変条件" },
    { id: "g2", label: "冪等性とリトライ" },
    { id: "g3", label: "ADR-0012 の DB 死活独立性ポリシー" },
  ],
  kc_before: 0.23,
  kc_after: 0.47,
  learning_plan_id: "plan-001",
};

export const QUIZ_LIST: QuizList = {
  quizzes: [
    {
      session_id: "quiz-user-service",
      file_path: "src/services/user-service.ts",
      repo_full_name: "demo/app",
      reason: "AI 生成 + レビューが形式的",
      question_count: 5,
      estimated_minutes: 8,
    },
    {
      session_id: "quiz-token-rotation",
      file_path: "src/auth/token-rotation.ts",
      repo_full_name: "demo/app",
      reason: "作者が離脱 · KC 0.31",
      question_count: 5,
      estimated_minutes: 6,
    },
  ],
};

export function mockQuizSession(sessionId: string): QuizSession | undefined {
  return SESSIONS[sessionId];
}

export function mockQuizResult(sessionId: string): QuizResult {
  return { ...RESULT, session_id: sessionId };
}
