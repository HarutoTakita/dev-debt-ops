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

export const overviewSchema = z.object({
  org: z.string(),
  generated_at: z.iso.datetime({ offset: true }),
  files: z.array(fileDebtSchema), // 散布図の点
  trend: z.array(debtTrendPointSchema), // 地層グラフ
  activity: weeklyActivitySchema, // 今週の活動
});

export type DebtPriority = z.infer<typeof debtPrioritySchema>;
export type FileDebt = z.infer<typeof fileDebtSchema>;
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
