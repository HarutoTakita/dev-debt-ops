import { z } from "zod";
import {
  analyzeStackJobSchema,
  branchListSchema,
  analysisStatusSchema,
  knowledgeUnitsSchema,
  debtItemSchema,
  debtListSchema,
  fileDebtSchema,
  fileContentSchema,
  codeWalkthroughSchema,
  codeWalkthroughJobSchema,
  codeGraphSchema,
  featureFunctionGraphSchema,
  fileFunctionGraphSchema,
  learningPlanSchema,
  learningStepSchema,
  overviewSchema,
  personalGalaxySchema,
  jobStatusSchema,
  orgMemberSchema,
  orgSchema,
  projectListSchema,
  projectSchema,
  quizAnswerSchema,
  quizListSchema,
  quizResultSchema,
  quizSessionSchema,
  repositoryListSchema,
  techStackSchema,
  treeSchema,
  type AnalyzeStackJob,
  type BranchList,
  type AnalysisStatus,
  type KnowledgeUnit,
  type DebtItem,
  type DebtList,
  type FileDebt,
  type LearningPlan,
  type LearningStep,
  type CodeWalkthrough,
  type CodeGraph,
  type FeatureFunctionGraph,
  type FileFunctionGraph,
  type Overview,
  type PersonalGalaxy,
  type FileContent,
  type JobStatusResponse,
  type Org,
  type OrgMember,
  type OrgRole,
  type Project,
  type QuizAnswer,
  type QuizList,
  type QuizResult,
  type QuizSession,
  type Repository,
  type RepositoryList,
  type Severity,
  type TechStack,
  type Tree,
} from "./schemas";

export type {
  AnalyzeStackJob,
  BranchList,
  FileContent,
  JobStatusResponse,
  Org,
  OrgMember,
  OrgRole,
  Project,
  Repository,
  RepositoryList,
  TechStack,
  Tree,
};

async function errorDetail(response: Response, fallback: string): Promise<string> {
  if (!response.headers.get("content-type")?.includes("application/json")) return fallback;
  try {
    const body: unknown = await response.json();
    if (typeof body === "object" && body !== null && "detail" in body && typeof body.detail === "string") {
      return body.detail;
    }
  } catch {
    /* non-JSON body */
  }
  return fallback;
}

let _refreshing: Promise<boolean> | null = null;

async function tryRefresh(): Promise<boolean> {
  if (_refreshing) return _refreshing;
  _refreshing = fetch("/api/v1/auth/refresh", { method: "POST" })
    .then((r) => r.ok)
    .finally(() => {
      _refreshing = null;
    });
  return _refreshing;
}

export async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const headers = new Headers(init?.headers);
  if (typeof init?.body === "string" && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  let response = await fetch(path, { ...init, headers });
  if (response.status === 401 && path !== "/api/v1/auth/refresh") {
    const refreshed = await tryRefresh();
    if (refreshed) {
      response = await fetch(path, { ...init, headers });
    } else {
      window.location.href = "/login";
    }
  }
  return response;
}

export async function listOrgs(): Promise<Org[]> {
  const response = await apiFetch("/api/v1/orgs");
  if (!response.ok) return [];
  return z.array(orgSchema).parse(await response.json());
}

// 公開ランタイム設定（認証前に SPA が参照）: デモボタンの出し分けに使う（issue 069）。
export async function getPublicConfig(): Promise<{ demo_mode_enabled: boolean }> {
  const response = await apiFetch("/api/v1/config");
  if (!response.ok) return { demo_mode_enabled: false };
  const data = (await response.json()) as { demo_mode_enabled?: boolean };
  return { demo_mode_enabled: Boolean(data.demo_mode_enabled) };
}

// ゲストデモログイン（issue 069）: GitHub 不要。共有デモユーザーとして cookie を発行する（204）。
export async function demoLogin(): Promise<void> {
  const response = await apiFetch("/api/v1/auth/demo", { method: "POST" });
  if (!response.ok) throw new Error(await errorDetail(response, "デモの開始に失敗しました"));
}

export async function createOrg(name: string, slug: string): Promise<Org> {
  const response = await apiFetch("/api/v1/orgs", {
    method: "POST",
    body: JSON.stringify({ name, slug }),
  });
  if (!response.ok) throw new Error(await errorDetail(response, "Failed to create organization"));
  return orgSchema.parse(await response.json());
}

export async function getMyMembership(orgSlug: string): Promise<OrgMember | null> {
  const response = await apiFetch(`/api/v1/orgs/${orgSlug}/me`);
  if (!response.ok) return null;
  return orgMemberSchema.parse(await response.json());
}

export async function listMembers(orgSlug: string): Promise<OrgMember[]> {
  const response = await apiFetch(`/api/v1/orgs/${orgSlug}/members`);
  if (!response.ok) throw new Error(await errorDetail(response, "Failed to load members"));
  return z.array(orgMemberSchema).parse(await response.json());
}

export async function inviteMember(orgSlug: string, email: string): Promise<OrgMember> {
  const response = await apiFetch(`/api/v1/orgs/${orgSlug}/members`, {
    method: "POST",
    body: JSON.stringify({ email }),
  });
  if (!response.ok) throw new Error(await errorDetail(response, "Failed to invite member"));
  return orgMemberSchema.parse(await response.json());
}

export async function patchMemberRole(orgSlug: string, userId: string, role: OrgRole): Promise<OrgMember> {
  const response = await apiFetch(`/api/v1/orgs/${orgSlug}/members/${userId}`, {
    method: "PATCH",
    body: JSON.stringify({ role }),
  });
  if (!response.ok) throw new Error(await errorDetail(response, "Failed to update role"));
  return orgMemberSchema.parse(await response.json());
}

export async function removeMember(orgSlug: string, userId: string): Promise<void> {
  const response = await apiFetch(`/api/v1/orgs/${orgSlug}/members/${userId}`, {
    method: "DELETE",
  });
  if (!response.ok) throw new Error(await errorDetail(response, "Failed to remove member"));
}

// Projects — リポジトリ単位の観測対象（1 プロジェクト = 1 リポジトリ）

export async function listProjects(orgSlug: string): Promise<Project[]> {
  const response = await apiFetch(`/api/v1/orgs/${orgSlug}/projects`);
  if (!response.ok) throw new Error(await errorDetail(response, "プロジェクトの取得に失敗しました"));
  return projectListSchema.parse(await response.json()).projects;
}

export async function getProject(orgSlug: string, projectSlug: string): Promise<Project | null> {
  const response = await apiFetch(`/api/v1/orgs/${orgSlug}/projects/${projectSlug}`);
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(await errorDetail(response, "プロジェクトの取得に失敗しました"));
  return projectSchema.parse(await response.json());
}

export async function createProject(
  orgSlug: string,
  name: string,
  repo: Repository,
  branch?: string,
  slug?: string,
): Promise<Project> {
  const response = await apiFetch(`/api/v1/orgs/${orgSlug}/projects`, {
    method: "POST",
    body: JSON.stringify({
      name,
      slug,
      repo_owner: repo.owner,
      repo_name: repo.name,
      repo_full_name: repo.full_name,
      // 解析対象ブランチ（未指定ならリポジトリの既定ブランチ）。
      default_branch: branch || repo.default_branch,
      repo_private: repo.private,
    }),
  });
  if (!response.ok) throw new Error(await errorDetail(response, "プロジェクトの作成に失敗しました"));
  return projectSchema.parse(await response.json());
}

export async function patchProject(
  orgSlug: string,
  projectSlug: string,
  patch: { name?: string; slug?: string; default_branch?: string },
): Promise<Project> {
  const response = await apiFetch(`/api/v1/orgs/${orgSlug}/projects/${projectSlug}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
  if (!response.ok) throw new Error(await errorDetail(response, "プロジェクトの更新に失敗しました"));
  return projectSchema.parse(await response.json());
}

export async function deleteProject(orgSlug: string, projectSlug: string): Promise<void> {
  const response = await apiFetch(`/api/v1/orgs/${orgSlug}/projects/${projectSlug}`, {
    method: "DELETE",
  });
  if (!response.ok) throw new Error(await errorDetail(response, "プロジェクトの削除に失敗しました"));
}

// GitHub

export class AppNotInstalledError extends Error {
  appSlug: string;
  constructor(appSlug: string) {
    super("GitHub App not installed");
    this.appSlug = appSlug;
  }
}

export async function listRepositories(page = 1, perPage = 30): Promise<RepositoryList> {
  const response = await apiFetch(`/api/v1/github/repositories?page=${page}&per_page=${perPage}`);
  if (response.status === 404) {
    const body: unknown = await response.json().catch(() => null);
    if (
      typeof body === "object" &&
      body !== null &&
      "detail" in body &&
      typeof body.detail === "object" &&
      body.detail !== null &&
      "reason" in body.detail &&
      body.detail.reason === "app_not_installed"
    ) {
      const slug = "app_slug" in body.detail && typeof body.detail.app_slug === "string" ? body.detail.app_slug : "";
      throw new AppNotInstalledError(slug);
    }
  }
  if (!response.ok) throw new Error(await errorDetail(response, "リポジトリの取得に失敗しました"));
  return repositoryListSchema.parse(await response.json());
}

export async function listBranches(owner: string, repo: string): Promise<BranchList> {
  const response = await apiFetch(`/api/v1/github/repositories/${owner}/${repo}/branches`);
  if (!response.ok) throw new Error(await errorDetail(response, "ブランチの取得に失敗しました"));
  return branchListSchema.parse(await response.json());
}

export async function getRepositoryTree(owner: string, repo: string, branch?: string): Promise<Tree> {
  const params = branch ? `?branch=${encodeURIComponent(branch)}` : "";
  const response = await apiFetch(`/api/v1/github/repositories/${owner}/${repo}/tree${params}`);
  if (!response.ok) throw new Error(await errorDetail(response, "ツリーの取得に失敗しました"));
  return treeSchema.parse(await response.json());
}

export async function getFileContent(owner: string, repo: string, path: string, ref?: string): Promise<FileContent> {
  const params = new URLSearchParams({ path });
  if (ref) params.set("ref", ref);
  const response = await apiFetch(`/api/v1/github/repositories/${owner}/${repo}/contents?${params}`);
  if (!response.ok) throw new Error(await errorDetail(response, "ファイルの取得に失敗しました"));
  return fileContentSchema.parse(await response.json());
}

// analyze-stack は非同期化（issue 018）: 202 {job_id} を返し、getJob でポーリングする。
export async function analyzeStack(owner: string, repo: string): Promise<AnalyzeStackJob> {
  const response = await apiFetch(`/api/v1/github/repositories/${owner}/${repo}/analyze-stack`, {
    method: "POST",
  });
  if (!response.ok) throw new Error(await errorDetail(response, "テックスタックの解析に失敗しました"));
  return analyzeStackJobSchema.parse(await response.json());
}

// detect-debts は非同期（issue 028）: 202 {job_id} を返し、getJob でポーリングする。
// 検知結果の一覧配信（listDebts / getDebt の差し替え）は 031 と連携。
export async function detectDebts(orgSlug: string, projectSlug: string): Promise<AnalyzeStackJob> {
  const response = await apiFetch(`/api/v1/orgs/${orgSlug}/projects/${projectSlug}/detect-debts`, {
    method: "POST",
  });
  if (!response.ok) throw new Error(await errorDetail(response, "コード負債の検知に失敗しました"));
  return analyzeStackJobSchema.parse(await response.json());
}

// detect-knowledge-debts は非同期（issue 030）: 202 {job_id} を返し、getJob でポーリングする。
// 検知結果の一覧配信（listDebts / getDebt の差し替え）は 031 と連携。
export async function detectKnowledgeDebts(orgSlug: string, projectSlug: string): Promise<AnalyzeStackJob> {
  const response = await apiFetch(`/api/v1/orgs/${orgSlug}/projects/${projectSlug}/detect-knowledge-debts`, {
    method: "POST",
  });
  if (!response.ok) throw new Error(await errorDetail(response, "知識負債の検知に失敗しました"));
  return analyzeStackJobSchema.parse(await response.json());
}

// agentic 解析（issue 069）: ADK Twin Agent を起動。202 {job_id} を返し、getJob でポーリングする。
export async function runAgenticAnalysis(orgSlug: string, projectSlug: string): Promise<AnalyzeStackJob> {
  const response = await apiFetch(`/api/v1/orgs/${orgSlug}/projects/${projectSlug}/agentic-analysis`, {
    method: "POST",
  });
  if (!response.ok) throw new Error(await errorDetail(response, "解析の開始に失敗しました"));
  return analyzeStackJobSchema.parse(await response.json());
}

// 機能クラスタリング（issue 052）: 202 {job_id} を返し getJob でポーリング。features/feature_files を生成し、
// 単元（063）・機能粒度ビュー（055/056）・機能スコープのクイズ（054）の前提になる。
export async function clusterFeatures(orgSlug: string, projectSlug: string): Promise<AnalyzeStackJob> {
  const response = await apiFetch(`/api/v1/orgs/${orgSlug}/projects/${projectSlug}/cluster-features`, {
    method: "POST",
  });
  if (!response.ok) throw new Error(await errorDetail(response, "機能クラスタリングに失敗しました"));
  return analyzeStackJobSchema.parse(await response.json());
}

export async function getJob(jobId: string): Promise<JobStatusResponse> {
  const response = await apiFetch(`/api/v1/jobs/${jobId}`);
  if (!response.ok) throw new Error(await errorDetail(response, "ジョブの取得に失敗しました"));
  return jobStatusSchema.parse(await response.json());
}

export async function getStack(owner: string, repo: string): Promise<TechStack | null> {
  const response = await apiFetch(`/api/v1/github/repositories/${owner}/${repo}/stack`);
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(await errorDetail(response, "テックスタックの取得に失敗しました"));
  return techStackSchema.parse(await response.json());
}

// Learning plan（issue 035）: 生成は 202+plan_id 即時発番、取得/ステップ進捗は実 API。
export async function generatePlan(
  orgSlug: string,
  projectSlug: string,
  opts: { attemptId?: string; gapConcepts?: string[]; featureId?: string } = {},
): Promise<{ job_id: string; plan_id: string }> {
  const qs = opts.attemptId ? `?attempt_id=${opts.attemptId}` : "";
  const response = await apiFetch(`/api/v1/orgs/${orgSlug}/projects/${projectSlug}/learning/plans${qs}`, {
    method: "POST",
    body: JSON.stringify({ gap_concepts: opts.gapConcepts ?? [], feature_id: opts.featureId ?? null }),
  });
  if (!response.ok) throw new Error(await errorDetail(response, "学習プラン生成の開始に失敗しました"));
  const data = (await response.json()) as { job_id: string; plan_id: string };
  return { job_id: String(data.job_id), plan_id: String(data.plan_id) };
}

export async function getLearningPlan(orgSlug: string, projectSlug: string, planId: string): Promise<LearningPlan> {
  const response = await apiFetch(`/api/v1/orgs/${orgSlug}/projects/${projectSlug}/learning/plans/${planId}`);
  if (response.status === 404) throw new Error("学習プランが見つかりません");
  if (!response.ok) throw new Error(await errorDetail(response, "学習プランの取得に失敗しました"));
  return learningPlanSchema.parse(await response.json());
}

export async function patchStep(
  orgSlug: string,
  projectSlug: string,
  planId: string,
  order: number,
  completed: boolean,
): Promise<LearningStep> {
  const response = await apiFetch(
    `/api/v1/orgs/${orgSlug}/projects/${projectSlug}/learning/plans/${planId}/steps/${order}`,
    { method: "PATCH", body: JSON.stringify({ completed }) },
  );
  if (!response.ok) throw new Error(await errorDetail(response, "ステップの更新に失敗しました"));
  return learningStepSchema.parse(await response.json());
}

// コード理解ウォークスルー（行ごと解説）: 保存済みを取得 / 未生成ならジョブを enqueue（オンデマンド生成）。
export async function getCodeWalkthrough(
  orgSlug: string,
  projectSlug: string,
  resourceId: string,
): Promise<CodeWalkthrough> {
  const response = await apiFetch(
    `/api/v1/orgs/${orgSlug}/projects/${projectSlug}/learning/resources/${resourceId}/walkthrough`,
  );
  if (response.status === 404) throw new Error("学習リソースが見つかりません");
  if (!response.ok) throw new Error(await errorDetail(response, "コード解説の取得に失敗しました"));
  return codeWalkthroughSchema.parse(await response.json());
}

export async function generateCodeWalkthrough(
  orgSlug: string,
  projectSlug: string,
  resourceId: string,
): Promise<{ job_id: string | null; status: string }> {
  const response = await apiFetch(
    `/api/v1/orgs/${orgSlug}/projects/${projectSlug}/learning/resources/${resourceId}/walkthrough`,
    { method: "POST" },
  );
  if (!response.ok) throw new Error(await errorDetail(response, "コード解説の生成開始に失敗しました"));
  return codeWalkthroughJobSchema.parse(await response.json());
}

// Knowledge Galaxy（issue 032）: GET .../galaxy を personalGalaxySchema で検証 / analyze-galaxy は enqueue。
export async function getGalaxy(orgSlug: string, projectSlug: string): Promise<PersonalGalaxy> {
  const response = await apiFetch(`/api/v1/orgs/${orgSlug}/projects/${projectSlug}/galaxy`);
  if (!response.ok) throw new Error(await errorDetail(response, "Galaxy の取得に失敗しました"));
  return personalGalaxySchema.parse(await response.json());
}

export async function analyzeGalaxy(orgSlug: string, projectSlug: string): Promise<AnalyzeStackJob> {
  const response = await apiFetch(`/api/v1/orgs/${orgSlug}/projects/${projectSlug}/analyze-galaxy`, {
    method: "POST",
  });
  if (!response.ok) throw new Error(await errorDetail(response, "理解度の算出開始に失敗しました"));
  return analyzeStackJobSchema.parse(await response.json());
}

// Overview 二軸集計（issue 031）: GET .../overview を取得して overviewSchema で検証。
// issue 055/056: granularity=feature|folder|file で機能/フォルダ単位のロールアップを取得。
export async function getOverview(
  orgSlug: string,
  projectSlug: string,
  granularity: "feature" | "folder" | "file" = "file",
): Promise<Overview> {
  const qs = granularity === "file" ? "" : `?granularity=${granularity}`;
  const response = await apiFetch(`/api/v1/orgs/${orgSlug}/projects/${projectSlug}/overview${qs}`);
  if (!response.ok) throw new Error(await errorDetail(response, "Overview の取得に失敗しました"));
  return overviewSchema.parse(await response.json());
}

// 機能単位の学習×確認クイズ単元（issue 063）: GET .../knowledge-units。
export async function getKnowledgeUnits(orgSlug: string, projectSlug: string): Promise<KnowledgeUnit[]> {
  const response = await apiFetch(`/api/v1/orgs/${orgSlug}/projects/${projectSlug}/knowledge-units`);
  if (!response.ok) throw new Error(await errorDetail(response, "単元の取得に失敗しました"));
  return knowledgeUnitsSchema.parse(await response.json()).units;
}

// 全機能のベースライン確認クイズを生成（issue 054/063）: POST .../baseline-quizzes → 202 {created, job_ids}。
export async function generateBaselineQuizzes(orgSlug: string, projectSlug: string): Promise<{ created: number }> {
  const response = await apiFetch(`/api/v1/orgs/${orgSlug}/projects/${projectSlug}/baseline-quizzes`, {
    method: "POST",
  });
  if (!response.ok) throw new Error(await errorDetail(response, "確認クイズの用意に失敗しました"));
  const data = (await response.json()) as { created?: number };
  return { created: Number(data.created ?? 0) };
}

// 機能ごとの学習プランを一括生成（issue 064）: 生成導線を「解析」に集約。baseline-quizzes と対称（N 件ファンアウト）。
export async function generateBaselinePlans(orgSlug: string, projectSlug: string): Promise<{ created: number }> {
  const response = await apiFetch(`/api/v1/orgs/${orgSlug}/projects/${projectSlug}/baseline-plans`, {
    method: "POST",
  });
  if (!response.ok) throw new Error(await errorDetail(response, "学習プランの一括生成に失敗しました"));
  const data = (await response.json()) as { created?: number };
  return { created: Number(data.created ?? 0) };
}

// 解析完了時に、現在のコード品質・理解度を週次の推移点として記録（upsert）する（issue 067）。
// 返り値（記録した点 or null）は使わない（記録のみ）。
export async function recordTrendSnapshot(orgSlug: string, projectSlug: string): Promise<void> {
  const response = await apiFetch(`/api/v1/orgs/${orgSlug}/projects/${projectSlug}/trend-snapshot`, {
    method: "POST",
  });
  if (!response.ok) throw new Error(await errorDetail(response, "推移スナップショットの記録に失敗しました"));
}

// 解析ステージの最新ジョブ状態（リロード後の状態復元用）: GET .../analysis-status。
export async function getAnalysisStatus(orgSlug: string, projectSlug: string): Promise<AnalysisStatus> {
  const response = await apiFetch(`/api/v1/orgs/${orgSlug}/projects/${projectSlug}/analysis-status`);
  if (!response.ok) throw new Error(await errorDetail(response, "解析状態の取得に失敗しました"));
  return analysisStatusSchema.parse(await response.json());
}

// 進行中（QUEUED/PROCESSING）の解析ジョブをキャンセルし、更新後の最新状態を返す。
export async function cancelAnalysis(orgSlug: string, projectSlug: string): Promise<AnalysisStatus> {
  const response = await apiFetch(`/api/v1/orgs/${orgSlug}/projects/${projectSlug}/cancel-analysis`, {
    method: "POST",
  });
  if (!response.ok) throw new Error(await errorDetail(response, "解析のキャンセルに失敗しました"));
  return analysisStatusSchema.parse(await response.json());
}

// 機能ドリルダウン（issue 055/056）: GET .../features/{feature_key} で機能配下ファイルの理解負債を取得。
export async function getFeatureDrilldown(
  orgSlug: string,
  projectSlug: string,
  featureKey: string,
): Promise<FileDebt[]> {
  const response = await apiFetch(
    `/api/v1/orgs/${orgSlug}/projects/${projectSlug}/features/${encodeURIComponent(featureKey)}`,
  );
  if (!response.ok) throw new Error(await errorDetail(response, "機能の詳細取得に失敗しました"));
  return z.array(fileDebtSchema).parse(await response.json());
}

// Debt registry（Matrix）— issue 031 で実 API に接続。フィルタ/ソートはクエリでサーバに委譲。
export type DebtFilter = {
  kind?: ("code" | "knowledge")[];
  severity?: Severity[];
  agent?: string[];
  status?: string[];
};
export type DebtSort = { key: "severity" | "detected_at" | "estimated_repay_hours"; dir: "asc" | "desc" };

export async function listDebts(
  orgSlug: string,
  projectSlug: string,
  filter: DebtFilter,
  sort: DebtSort,
): Promise<DebtList> {
  const params = new URLSearchParams();
  for (const k of filter.kind ?? []) params.append("kind", k);
  for (const s of filter.severity ?? []) params.append("severity", s);
  for (const a of filter.agent ?? []) params.append("agent", a);
  for (const st of filter.status ?? []) params.append("status", st);
  params.set("sort_key", sort.key);
  params.set("sort_dir", sort.dir);
  const response = await apiFetch(`/api/v1/orgs/${orgSlug}/projects/${projectSlug}/debts?${params}`);
  if (!response.ok) throw new Error(await errorDetail(response, "負債一覧の取得に失敗しました"));
  return debtListSchema.parse(await response.json());
}

export async function getDebt(orgSlug: string, projectSlug: string, debtId: string): Promise<DebtItem> {
  const response = await apiFetch(`/api/v1/orgs/${orgSlug}/projects/${projectSlug}/debts/${debtId}`);
  if (response.status === 404) throw new Error("負債が見つかりません");
  if (!response.ok) throw new Error(await errorDetail(response, "負債の取得に失敗しました"));
  return debtItemSchema.parse(await response.json());
}

// 修正 PR 生成（issue 033/215）: POST .../debts/{id}/repayment-pr → 202 {job_id}、getJob でポーリング。
// baseBranch で PR 先ブランチを指定（未指定ならプロジェクトの解析対象ブランチ）。
export async function createRepaymentPr(
  orgSlug: string,
  projectSlug: string,
  debtId: string,
  baseBranch?: string,
): Promise<AnalyzeStackJob> {
  const response = await apiFetch(`/api/v1/orgs/${orgSlug}/projects/${projectSlug}/debts/${debtId}/repayment-pr`, {
    method: "POST",
    body: JSON.stringify({ base_branch: baseBranch ?? null }),
  });
  if (!response.ok) throw new Error(await errorDetail(response, "修正 PR の作成に失敗しました"));
  return analyzeStackJobSchema.parse(await response.json());
}
// 人に頼む経路（issue 210）: GitHub issue を作成する。任意でワークスペースのユーザーを担当に指定できる
// （assigneeUserId）。POST .../debts/{id}/issue → 更新後の DebtItem（related_issue にissue URLが入る）。
export async function createDebtIssue(
  orgSlug: string,
  projectSlug: string,
  debtId: string,
  assigneeUserId?: string,
): Promise<DebtItem> {
  const response = await apiFetch(`/api/v1/orgs/${orgSlug}/projects/${projectSlug}/debts/${debtId}/issue`, {
    method: "POST",
    body: JSON.stringify({ assignee_user_id: assigneeUserId ?? null }),
  });
  if (!response.ok) throw new Error(await errorDetail(response, "GitHub Issue の作成に失敗しました"));
  return debtItemSchema.parse(await response.json());
}

// Quiz（返済体験、issue 034）— 実 API。生成/採点は 202 enqueue + getJob ポーリング。
export async function listQuizzes(orgSlug: string, projectSlug: string): Promise<QuizList> {
  const response = await apiFetch(`/api/v1/orgs/${orgSlug}/projects/${projectSlug}/quizzes`);
  if (!response.ok) throw new Error(await errorDetail(response, "クイズ一覧の取得に失敗しました"));
  return quizListSchema.parse(await response.json());
}

export async function generateQuiz(orgSlug: string, projectSlug: string, filePath: string): Promise<AnalyzeStackJob> {
  const response = await apiFetch(`/api/v1/orgs/${orgSlug}/projects/${projectSlug}/quizzes/generate`, {
    method: "POST",
    body: JSON.stringify({ file_path: filePath }),
  });
  if (!response.ok) throw new Error(await errorDetail(response, "クイズ生成の開始に失敗しました"));
  return analyzeStackJobSchema.parse(await response.json());
}

export async function getQuizSession(orgSlug: string, projectSlug: string, sessionId: string): Promise<QuizSession> {
  const response = await apiFetch(`/api/v1/orgs/${orgSlug}/projects/${projectSlug}/quizzes/${sessionId}`);
  if (response.status === 404) throw new Error("クイズが見つかりません");
  if (!response.ok) throw new Error(await errorDetail(response, "クイズの取得に失敗しました"));
  return quizSessionSchema.parse(await response.json());
}

export async function saveQuizAnswer(
  orgSlug: string,
  projectSlug: string,
  sessionId: string,
  answer: QuizAnswer,
): Promise<QuizAnswer> {
  const response = await apiFetch(`/api/v1/orgs/${orgSlug}/projects/${projectSlug}/quizzes/${sessionId}/answers`, {
    method: "PATCH",
    body: JSON.stringify({ question_id: answer.question_id, value: answer.value }),
  });
  if (!response.ok) throw new Error(await errorDetail(response, "回答の保存に失敗しました"));
  return quizAnswerSchema.parse(await response.json());
}

// submit は 202 化（issue 034）: job を返し、getJob ポーリング後に getQuizResult で結果を取得する。
// 既に提出済み（採点中/採点済み）のセッションを再提出すると 409 になるため、その場合は再提出せず
// 結果取得へ進めるよう null を返す（結果ページの load がリロード等で再実行されても 500 にしない）。
export async function submitQuiz(
  orgSlug: string,
  projectSlug: string,
  sessionId: string,
): Promise<AnalyzeStackJob | null> {
  const response = await apiFetch(`/api/v1/orgs/${orgSlug}/projects/${projectSlug}/quizzes/${sessionId}/submit`, {
    method: "POST",
  });
  if (response.status === 409) return null; // 既に提出済み → 再提出しない
  if (!response.ok) throw new Error(await errorDetail(response, "採点の開始に失敗しました"));
  return analyzeStackJobSchema.parse(await response.json());
}

// 採点中はまだ結果が無く 404。その場合は null を返し、呼び出し側で完了までポーリングする。
export async function getQuizResult(
  orgSlug: string,
  projectSlug: string,
  sessionId: string,
): Promise<QuizResult | null> {
  const response = await apiFetch(`/api/v1/orgs/${orgSlug}/projects/${projectSlug}/quizzes/${sessionId}/result`);
  if (response.status === 404) return null; // 採点中（結果未確定）
  if (!response.ok) throw new Error(await errorDetail(response, "採点結果の取得に失敗しました"));
  return quizResultSchema.parse(await response.json());
}

// コードグラフ（issue 235）: agentic 解析が構築・永続化したスナップショットを取得（将来 UI 用）。
export async function getCodeGraph(orgSlug: string, projectSlug: string): Promise<CodeGraph> {
  const response = await apiFetch(`/api/v1/orgs/${orgSlug}/projects/${projectSlug}/code-graph`);
  if (!response.ok) throw new Error(await errorDetail(response, "コードグラフの取得に失敗しました"));
  return codeGraphSchema.parse(await response.json());
}

// ファイル内関数コールグラフ（Level-3, issue 240）: ファイルノードのクリック時に遅延取得。
export async function getFileFunctionGraph(
  orgSlug: string,
  projectSlug: string,
  path: string,
): Promise<FileFunctionGraph> {
  const params = new URLSearchParams({ path });
  const response = await apiFetch(`/api/v1/orgs/${orgSlug}/projects/${projectSlug}/code-graph/file?${params}`);
  if (!response.ok) throw new Error(await errorDetail(response, "関数グラフの取得に失敗しました"));
  return fileFunctionGraphSchema.parse(await response.json());
}

// 機能の関数レベルグラフ（Level-2, issue 282）: 機能ノードのクリック時に遅延取得。
export async function getFeatureFunctionGraph(
  orgSlug: string,
  projectSlug: string,
  featureKey: string,
): Promise<FeatureFunctionGraph> {
  const params = new URLSearchParams({ key: featureKey });
  const response = await apiFetch(`/api/v1/orgs/${orgSlug}/projects/${projectSlug}/code-graph/feature?${params}`);
  if (!response.ok) throw new Error(await errorDetail(response, "機能グラフの取得に失敗しました"));
  return featureFunctionGraphSchema.parse(await response.json());
}
