import { z } from "zod";

export const userSchema = z.object({
  id: z.uuid(),
  email: z.string(),
  display_name: z.string().nullable(),
  is_active: z.boolean(),
  is_superuser: z.boolean(),
  is_verified: z.boolean(),
  created_at: z.iso.datetime({ offset: true }).nullable().optional(),
  last_active_at: z.iso.datetime({ offset: true }).nullable().optional(),
});

export const orgSchema = z.object({
  id: z.uuid(),
  name: z.string(),
  slug: z.string(),
  is_personal: z.boolean(),
  created_by: z.uuid(),
  created_at: z.iso.datetime({ offset: true }),
});

export const orgRoleSchema = z.enum(["owner", "admin", "member"]);

export const orgMemberUserSchema = z.object({
  id: z.uuid(),
  email: z.string(),
  display_name: z.string().nullable(),
  last_active_at: z.iso.datetime({ offset: true }).nullable().optional(),
  is_active: z.boolean(),
});

export const orgMemberSchema = z.object({
  id: z.uuid(),
  user_id: z.uuid(),
  org_id: z.uuid(),
  role: orgRoleSchema,
  created_at: z.iso.datetime({ offset: true }),
  user: orgMemberUserSchema,
});

export type User = z.infer<typeof userSchema>;
export type Org = z.infer<typeof orgSchema>;
export type OrgRole = z.infer<typeof orgRoleSchema>;
export type OrgMember = z.infer<typeof orgMemberSchema>;

// GitHub
export const repositorySchema = z.object({
  owner: z.string(),
  name: z.string(),
  full_name: z.string(),
  default_branch: z.string(),
  private: z.boolean(),
  updated_at: z.string(),
});

export const repositoryListSchema = z.object({
  repositories: z.array(repositorySchema),
  page: z.number(),
  has_more: z.boolean(),
});

export const branchSchema = z.object({
  name: z.string(),
  is_default: z.boolean(),
});

export const branchListSchema = z.object({
  branches: z.array(branchSchema),
});

export const treeItemSchema = z.object({
  path: z.string(),
  type: z.enum(["blob", "tree"]),
  size: z.number().nullable().optional(),
});

export const treeSchema = z.object({
  tree: z.array(treeItemSchema),
  branch: z.string(),
  truncated: z.boolean(),
});

export const fileContentSchema = z.object({
  path: z.string(),
  content: z.string().nullable(),
  sha: z.string(),
  size: z.number(),
});

export type Repository = z.infer<typeof repositorySchema>;
export type RepositoryList = z.infer<typeof repositoryListSchema>;
export type Branch = z.infer<typeof branchSchema>;
export type BranchList = z.infer<typeof branchListSchema>;
export type TreeItem = z.infer<typeof treeItemSchema>;
export type Tree = z.infer<typeof treeSchema>;
export type FileContent = z.infer<typeof fileContentSchema>;

// Project — observed git repository within an org (1 project == 1 repository)
export const projectSchema = z.object({
  id: z.uuid(),
  org_id: z.uuid(),
  name: z.string(),
  slug: z.string(),
  repo_owner: z.string(),
  repo_name: z.string(),
  repo_full_name: z.string(),
  default_branch: z.string(),
  repo_private: z.boolean(),
  github_repo_id: z.number().nullable().optional(),
  created_by: z.uuid(),
  created_at: z.iso.datetime({ offset: true }),
});

export const projectListSchema = z.object({
  projects: z.array(projectSchema),
});

export type Project = z.infer<typeof projectSchema>;
export type ProjectList = z.infer<typeof projectListSchema>;

// Tech Stack
export const techItemSchema = z.object({
  name: z.string(),
  confidence: z.enum(["high", "medium", "low"]),
});

export const techCategoriesSchema = z.object({
  frameworks: z.array(techItemSchema),
  databases: z.array(techItemSchema),
  auth: z.array(techItemSchema),
  container: z.array(techItemSchema),
  infra: z.array(techItemSchema),
  cicd: z.array(techItemSchema),
  monitoring: z.array(techItemSchema),
  testing: z.array(techItemSchema),
  other: z.array(techItemSchema),
});

export const techStackSchema = z.object({
  owner: z.string(),
  repo: z.string(),
  analyzed_at: z.iso.datetime({ offset: true }),
  languages: z.array(techItemSchema),
  categories: techCategoriesSchema,
});

export type TechItem = z.infer<typeof techItemSchema>;
export type TechCategories = z.infer<typeof techCategoriesSchema>;
export type TechStack = z.infer<typeof techStackSchema>;

// Async jobs（issue 018）— analyze-stack は enqueue + ポーリングに変更。
// status は backend の JobStatus（大文字 enum）に揃える。
export const jobStatusEnum = z.enum(["QUEUED", "PROCESSING", "COMPLETED", "FAILED", "CANCELLED"]);

// POST analyze-stack の 202 レスポンス（job_id + status）。
export const analyzeStackJobSchema = z.object({
  job_id: z.uuid(),
  status: jobStatusEnum,
});

// GET /jobs/{id} のポーリングレスポンス（status + 進捗 trace + 完了時 tech_stack）。
export const jobStatusSchema = z.object({
  id: z.uuid(),
  status: jobStatusEnum,
  agent_trace: z.array(z.string()).default([]),
  tech_stack: techStackSchema.nullable().optional(),
  error: z.string().nullable().optional(),
});

export type JobStatusValue = z.infer<typeof jobStatusEnum>;
export type AnalyzeStackJob = z.infer<typeof analyzeStackJobSchema>;
export type JobStatusResponse = z.infer<typeof jobStatusSchema>;

// Overview（観測台）— 二軸負債ダッシュボード。集計バックエンドは未実装のため、
// ここではフロントが期待する型だけを先に確定させる（後続 issue の集計 API がこの形に合わせる）。
export const debtPrioritySchema = z.enum(["P0", "P1", "P2", "P3"]);

// 二軸プレーンの 1 点 = 1 ファイル
export const fileDebtSchema = z.object({
  path: z.string(),
  language: z.string(),
  code_debt_score: z.number(), // 0..1 高いほど汚い
  knowledge_coverage: z.number(), // 0..1 高いほど皆理解（= KC）
  business_impact: z.number(), // 0..1
  priority: debtPrioritySchema, // §2.3 priority = code_debt × knowledge_debt × business_impact
});

export const debtTrendPointSchema = z.object({
  week: z.string(), // ISO 週 or ラベル
  code_debt_score: z.number(),
  knowledge_coverage: z.number(),
});

export const weeklyActivitySchema = z.object({
  code_agent_prs: z.number(),
  code_agent_merged: z.number(),
  knowledge_agent_quizzes: z.number(),
  knowledge_agent_passed: z.number(),
});

// 機能 / フォルダ単位のロールアップノード（issue 055 配信、issue 056 が消費）。snake_case 維持。
export const featureDebtSchema = z.object({
  key: z.string(),
  name: z.string(),
  granularity: z.string(),
  code_debt_score: z.number(),
  knowledge_coverage: z.number(),
  priority: debtPrioritySchema,
  file_count: z.number(),
  weakest_file: z.string().nullable().default(null),
});

export const overviewSchema = z.object({
  org: z.string(),
  generated_at: z.iso.datetime({ offset: true }),
  granularity: z.string().default("file"), // issue 055
  files: z.array(fileDebtSchema), // 散布図の点
  features: z.array(featureDebtSchema).default([]), // 機能/フォルダ単位ノード（issue 055）
  trend: z.array(debtTrendPointSchema), // 地層グラフ
  activity: weeklyActivitySchema, // 今週の活動
});

// 解析ステージごとの最新ジョブ状態（リロード後の状態復元用）。JobType 値でキー。
export const analysisStatusSchema = z.object({
  jobs: z.record(z.string(), z.object({ status: z.string(), job_id: z.string() })),
});

// 機能（feature）単位の学習×確認クイズ単元（issue 063）。
export const knowledgeUnitSchema = z.object({
  feature_id: z.string(),
  feature_key: z.string(),
  name: z.string(),
  knowledge_coverage: z.number(),
  code_debt_score: z.number(),
  file_count: z.number(),
  status: z.string(), // unstarted | in_progress | verified | needs_review
  learning_plan_id: z.string().nullable().default(null),
  quiz_session_id: z.string().nullable().default(null),
  quiz_status: z.string().nullable().default(null),
});
export const knowledgeUnitsSchema = z.object({ units: z.array(knowledgeUnitSchema) });

export type DebtPriority = z.infer<typeof debtPrioritySchema>;
export type FileDebt = z.infer<typeof fileDebtSchema>;
export type FeatureDebt = z.infer<typeof featureDebtSchema>;
export type AnalysisStatus = z.infer<typeof analysisStatusSchema>;
export type KnowledgeUnit = z.infer<typeof knowledgeUnitSchema>;
export type DebtTrendPoint = z.infer<typeof debtTrendPointSchema>;
export type WeeklyActivity = z.infer<typeof weeklyActivitySchema>;
export type Overview = z.infer<typeof overviewSchema>;

// 負債レジストリ（Matrix の二次ビュー）。§7.1 の CodeDebt / KnowledgeDebt の UI 投影スキーマ。
// 意図的な変形: severity を float→enum に量子化 / file_id を file_path+repo に平坦化 /
// assigned_developers を CodeDebt にも拡張（理解者/形式レビューの視覚区別のため）。
// code_snippet は詳細ビューの該当コード表示用（file-viewer 再利用）に UI 投影として追加。
export const severitySchema = z.enum(["critical", "high", "medium", "low"]);
export const debtKindSchema = z.enum(["code", "knowledge"]);
export const certifiedViaSchema = z.enum(["quiz", "authorship", "review"]);

export const assignedDeveloperSchema = z.object({
  github_handle: z.string(),
  coverage: z.number().min(0).max(1), // KC(file, dev)
  certified_via: certifiedViaSchema, // quiz/authorship=理解者 / review=形式レビューのみ
});

export const codeDebtSchema = z.object({
  id: z.string(),
  kind: z.literal("code"),
  file_path: z.string(),
  repo: z.string(),
  type: z.enum(["duplicate", "dead", "complexity", "other"]),
  severity: severitySchema,
  status: z.enum(["open", "in_pr", "resolved", "dismissed"]),
  detected_at: z.iso.datetime({ offset: true }),
  related_pr: z.string().nullable(),
  related_adr: z.string().nullable(),
  archaeology_notes: z.string(),
  code_snippet: z.string(),
  code_debt_score: z.number().min(0).max(1),
  knowledge_coverage: z.number().min(0).max(1), // KC(file)
  ai_generation_prob: z.number().min(0).max(1),
  estimated_repay_hours: z.number(),
  assigned_agent: z.literal("code_debt"),
  assigned_developers: z.array(assignedDeveloperSchema),
});

export const knowledgeDebtSchema = z.object({
  id: z.string(),
  kind: z.literal("knowledge"),
  file_path: z.string(),
  repo: z.string(),
  reason: z.enum(["ai_generated", "author_left", "no_review", "other"]),
  severity: severitySchema,
  status: z.enum(["open", "in_progress", "resolved"]),
  detected_at: z.iso.datetime({ offset: true }),
  related_adr: z.string().nullable(),
  code_snippet: z.string(),
  code_debt_score: z.number().min(0).max(1),
  knowledge_coverage: z.number().min(0).max(1),
  ai_generation_prob: z.number().min(0).max(1),
  estimated_repay_hours: z.number(),
  assigned_agent: z.literal("knowledge_debt"),
  assigned_developers: z.array(assignedDeveloperSchema),
});

export const debtItemSchema = z.discriminatedUnion("kind", [codeDebtSchema, knowledgeDebtSchema]);
export const debtListSchema = z.object({
  debts: z.array(debtItemSchema),
  total: z.number(),
});

export type Severity = z.infer<typeof severitySchema>;
export type DebtKind = z.infer<typeof debtKindSchema>;
export type CertifiedVia = z.infer<typeof certifiedViaSchema>;
export type AssignedDeveloper = z.infer<typeof assignedDeveloperSchema>;
export type CodeDebt = z.infer<typeof codeDebtSchema>;
export type KnowledgeDebt = z.infer<typeof knowledgeDebtSchema>;
export type DebtItem = z.infer<typeof debtItemSchema>;
export type DebtList = z.infer<typeof debtListSchema>;

// Knowledge Galaxy（個人理解度マップ / §6.2）。3D は Future、本フェーズは 2D。
// 星=マスター / 薄星=部分理解 / ブラックホール=触ったが未理解 / 未踏星域=未接触。
export const masteryStatusSchema = z.enum(["star", "dim_star", "black_hole", "unexplored"]);

export const fileMasterySchema = z.object({
  path: z.string(), // ファイルパス（= 星）
  module: z.string(), // モジュール / ディレクトリ（= 星系）
  kc: z.number().min(0).max(1), // Knowledge Coverage ∈ [0,1]（§5.1）
  mastery: masteryStatusSchema,
  // §5.5 個人認定の簡易版: クイズ未連携のため mastery==="star" を「マスター済み」表示
  mastered: z.boolean().default(false),
});

export const wormholeSchema = z.object({
  from: z.string(), // 依存元ファイルパス
  to: z.string(), // 依存先ファイルパス
});

export const starSystemSchema = z.object({
  module: z.string(),
  kc: z.number().min(0).max(1), // 星系（モジュール）集計 KC = §5.1 の KC(file) 平均
  files: z.array(fileMasterySchema),
});

export const personalGalaxySchema = z.object({
  developer: z.string(),
  org_kc: z.number().min(0).max(1), // サイドバー pill 用の自分の KC%
  observed: z.boolean(), // false の場合は ComingSoonPlaceholder を出す
  systems: z.array(starSystemSchema),
  wormholes: z.array(wormholeSchema),
});

export type MasteryStatus = z.infer<typeof masteryStatusSchema>;
export type FileMastery = z.infer<typeof fileMasterySchema>;
export type Wormhole = z.infer<typeof wormholeSchema>;
export type StarSystem = z.infer<typeof starSystemSchema>;
export type PersonalGalaxy = z.infer<typeof personalGalaxySchema>;

// Quiz（返済体験 / §6.4・§7.1 QuizSession）。クイズ合格で KC が上がる Re:Pay の演出を担う。
export const conceptSchema = z.object({ id: z.string(), label: z.string() });

export const quizQuestionSchema = z.object({
  id: z.string(),
  kind: z.enum(["multiple_choice", "multiple_select"]),
  prompt: z.string(),
  code_snippet: z.object({ language: z.string(), path: z.string(), content: z.string() }).nullable(),
  choices: z.array(z.object({ id: z.string(), label: z.string() })).optional(),
  difficulty: z.enum(["L1", "L2", "L3", "L4", "L5"]),
});

export const quizAnswerSchema = z.object({
  question_id: z.string(),
  value: z.string(),
  saved_at: z.iso.datetime({ offset: true }),
});

export const quizSessionSchema = z.object({
  id: z.string(),
  developer_id: z.string(),
  file: z.object({ path: z.string(), repo_full_name: z.string() }),
  questions: z.array(quizQuestionSchema),
  answers: z.array(quizAnswerSchema),
  status: z.enum(["not_started", "in_progress", "grading", "completed"]),
  started_at: z.iso.datetime({ offset: true }).nullable(),
  completed_at: z.iso.datetime({ offset: true }).nullable(),
  score: z.number().nullable(),
});

export const quizResultSchema = z.object({
  session_id: z.string(),
  understood: z.array(conceptSchema), // あなたが理解していたこと
  gap_concepts: z.array(conceptSchema), // 学ぶ余地
  kc_before: z.number(), // 例: 0.23
  kc_after: z.number(), // 例: 0.47
  learning_plan_id: z.string().nullable(),
});

export const quizListItemSchema = z.object({
  session_id: z.string(),
  file_path: z.string(),
  repo_full_name: z.string(),
  reason: z.string(), // KC が低い理由（§5.1）
  question_count: z.number(),
  estimated_minutes: z.number(),
});
export const quizListSchema = z.object({ quizzes: z.array(quizListItemSchema) });

export type Concept = z.infer<typeof conceptSchema>;
export type QuizQuestion = z.infer<typeof quizQuestionSchema>;
export type QuizAnswer = z.infer<typeof quizAnswerSchema>;
export type QuizSession = z.infer<typeof quizSessionSchema>;
export type QuizResult = z.infer<typeof quizResultSchema>;
export type QuizListItem = z.infer<typeof quizListItemSchema>;
export type QuizList = z.infer<typeof quizListSchema>;

// Learning Plan（§5.4）。origin で「チーム資産(team)」を外部資源(external)より上に浮上させる。
export const resourceOriginSchema = z.enum(["team", "external"]);
export const resourceKindSchema = z.enum(["adr", "video", "pr_comment", "wiki", "docs", "book", "article", "code"]);
export const resourcePrioritySchema = z.enum(["required", "recommended", "supplementary", "hands_on"]);

export const learningResourceSchema = z.object({
  id: z.string(),
  origin: resourceOriginSchema, // "team" を最優先で上に表示
  kind: resourceKindSchema,
  title: z.string(),
  source_ref: z.string().nullable(), // ADR-0012 / PR #4523 / @alice 勉強会 等
  url: z.string().nullable(),
  estimated_minutes: z.number().nullable(),
  priority: resourcePrioritySchema,
  // 死蔵バッジ: 最後に閲覧されてからの経過（チーム資産の再活性化を可視化）
  dormant_days: z.number().nullable().optional(),
});

export const learningStepSchema = z.object({
  order: z.number(),
  resource: learningResourceSchema,
  completed: z.boolean(),
});

export const learningPlanSchema = z.object({
  id: z.string(),
  gap_concepts: z.array(z.string()), // ["distributed_caching", "ADR-0012", "RedisClient"]
  steps: z.array(learningStepSchema),
  estimated_total_minutes: z.number(),
});

export type ResourceOrigin = z.infer<typeof resourceOriginSchema>;
export type ResourceKind = z.infer<typeof resourceKindSchema>;
export type ResourcePriority = z.infer<typeof resourcePrioritySchema>;
export type LearningResource = z.infer<typeof learningResourceSchema>;
export type LearningStep = z.infer<typeof learningStepSchema>;
export type LearningPlan = z.infer<typeof learningPlanSchema>;
