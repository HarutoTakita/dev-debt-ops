import { z } from "zod";
import {
  branchListSchema,
  fileContentSchema,
  orgMemberSchema,
  orgSchema,
  repositoryListSchema,
  treeSchema,
  type BranchList,
  type FileContent,
  type Org,
  type OrgMember,
  type OrgRole,
  type Repository,
  type RepositoryList,
  type Tree,
} from "./schemas";

export type { BranchList, FileContent, Org, OrgMember, OrgRole, Repository, RepositoryList, Tree };

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

export async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const headers = new Headers(init?.headers);
  if (typeof init?.body === "string" && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  return fetch(path, { ...init, headers });
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
