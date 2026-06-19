import { z } from "zod";
import {
  branchListSchema,
  debtItemSchema,
  debtListSchema,
  fileContentSchema,
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
  type BranchList,
  type DebtItem,
  type DebtList,
  type FileContent,
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
import { MOCK_DEBTS } from "./mock/debts";
import { QUIZ_LIST, mockQuizResult, mockQuizSession } from "./quiz-mock";

export type { BranchList, FileContent, Org, OrgMember, OrgRole, Project, Repository, RepositoryList, TechStack, Tree };

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

export async function createProject(orgSlug: string, name: string, repo: Repository, slug?: string): Promise<Project> {
  const response = await apiFetch(`/api/v1/orgs/${orgSlug}/projects`, {
    method: "POST",
    body: JSON.stringify({
      name,
      slug,
      repo_owner: repo.owner,
      repo_name: repo.name,
      repo_full_name: repo.full_name,
      default_branch: repo.default_branch,
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

export async function analyzeStack(owner: string, repo: string): Promise<TechStack> {
  const response = await apiFetch(`/api/v1/github/repositories/${owner}/${repo}/analyze-stack`, {
    method: "POST",
  });
  if (!response.ok) throw new Error(await errorDetail(response, "テックスタックの解析に失敗しました"));
  return techStackSchema.parse(await response.json());
}

export async function getStack(owner: string, repo: string): Promise<TechStack | null> {
  const response = await apiFetch(`/api/v1/github/repositories/${owner}/${repo}/stack`);
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(await errorDetail(response, "テックスタックの取得に失敗しました"));
  return techStackSchema.parse(await response.json());
}

// Debt registry（Matrix）— 取得系はモック返却。シグネチャは本実装と互換にしておき、
// 後で GET /api/v1/orgs/{slug}/debts に差し替える。アクション系は Coming Soon スタブ。

export type DebtFilter = {
  kind?: ("code" | "knowledge")[];
  severity?: Severity[];
  agent?: string[];
  status?: string[];
};
export type DebtSort = { key: "severity" | "detected_at" | "estimated_repay_hours"; dir: "asc" | "desc" };

const SEVERITY_RANK: Record<Severity, number> = { critical: 3, high: 2, medium: 1, low: 0 };

function applyFilterSort(debts: DebtItem[], filter: DebtFilter, sort: DebtSort): DebtItem[] {
  const filtered = debts.filter((d) => {
    if (filter.kind?.length && !filter.kind.includes(d.kind)) return false;
    if (filter.severity?.length && !filter.severity.includes(d.severity)) return false;
    if (filter.agent?.length && !filter.agent.includes(d.assigned_agent)) return false;
    if (filter.status?.length && !filter.status.includes(d.status)) return false;
    return true;
  });
  const dir = sort.dir === "asc" ? 1 : -1;
  return filtered.sort((a, b) => {
    const cmp =
      sort.key === "severity"
        ? SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity]
        : sort.key === "detected_at"
          ? a.detected_at.localeCompare(b.detected_at)
          : a.estimated_repay_hours - b.estimated_repay_hours;
    return cmp * dir;
  });
}

export async function listDebts(orgSlug: string, filter: DebtFilter, sort: DebtSort): Promise<DebtList> {
  void orgSlug; // TODO: GET /api/v1/orgs/${orgSlug}/debts に差し替え。現状はモックをフィルタ/ソート。
  const debts = applyFilterSort(MOCK_DEBTS, filter, sort);
  return debtListSchema.parse({ debts, total: debts.length });
}

export async function getDebt(orgSlug: string, debtId: string): Promise<DebtItem> {
  void orgSlug;
  const found = MOCK_DEBTS.find((d) => d.id === debtId);
  if (!found) throw new Error("負債が見つかりません");
  return debtItemSchema.parse(found);
}

// --- Coming Soon（場所だけ用意・本体は未実装） ---
export class ComingSoonError extends Error {
  constructor() {
    super("coming_soon");
    this.name = "ComingSoonError";
  }
}
export async function createRepaymentPr(orgSlug: string, debtId: string): Promise<never> {
  void orgSlug;
  void debtId;
  throw new ComingSoonError();
}
export async function dismissDebt(orgSlug: string, debtId: string): Promise<never> {
  void orgSlug;
  void debtId;
  throw new ComingSoonError();
}
export async function assignDebt(orgSlug: string, debtId: string, handle: string): Promise<never> {
  void orgSlug;
  void debtId;
  void handle;
  throw new ComingSoonError();
}

// Quiz（返済体験）— 取得系はモック返却。シグネチャは本実装と互換にしておく。

export async function listQuizzes(orgSlug: string): Promise<QuizList> {
  void orgSlug; // TODO: 実 API 接続は後続 issue
  return quizListSchema.parse(QUIZ_LIST);
}

export async function getQuizSession(sessionId: string): Promise<QuizSession> {
  const session = mockQuizSession(sessionId);
  if (!session) throw new Error("クイズが見つかりません");
  return quizSessionSchema.parse(session);
}

export async function saveQuizAnswer(sessionId: string, answer: QuizAnswer): Promise<QuizAnswer> {
  void sessionId; // TODO: PATCH 実 API は後続 issue。今は楽観的に保存済みを返す
  return quizAnswerSchema.parse(answer);
}

export async function submitQuiz(sessionId: string): Promise<QuizResult> {
  // TODO: 実採点は後続 issue。今はモック結果（KC 0.23 → 0.47）を返す
  return quizResultSchema.parse(mockQuizResult(sessionId));
}
