import { z } from "zod";
import { orgSchema, orgMemberSchema, type Org, type OrgMember, type OrgRole } from "./schemas";

export type { Org, OrgMember, OrgRole };

async function errorDetail(response: Response, fallback: string): Promise<string> {
  if (!response.headers.get("content-type")?.includes("application/json")) return fallback;
  try {
    const body: unknown = await response.json();
    if (
      typeof body === "object" &&
      body !== null &&
      "detail" in body &&
      typeof body.detail === "string"
    ) {
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

export async function patchMemberRole(
  orgSlug: string,
  userId: string,
  role: OrgRole,
): Promise<OrgMember> {
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
