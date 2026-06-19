import { beforeEach, describe, expect, it, vi } from "vitest";
import type { OrgMember, OrgRole } from "$lib/api/schemas";

// API クライアントをモック（vi.hoisted で factory より前に確実に生成）。
const mocks = vi.hoisted(() => ({
  listMembers: vi.fn(),
  inviteMember: vi.fn(),
  patchMemberRole: vi.fn(),
  removeMember: vi.fn(),
  getMyMembership: vi.fn(),
}));
vi.mock("$lib/api/client", () => mocks);

import { members } from "./members-store.svelte";

function makeMember(id: string, role: OrgRole): OrgMember {
  return {
    id,
    user_id: `u-${id}`,
    org_id: "o",
    role,
    created_at: "2026-01-01T00:00:00+09:00",
    user: { id: `u-${id}`, email: `${id}@example.com`, display_name: id, is_active: true },
  };
}

beforeEach(() => {
  members.members = [];
  members.myRole = null;
  members.loading = false;
  vi.clearAllMocks();
});

describe("MembersStore", () => {
  it("load() fills members from the API and clears loading", async () => {
    mocks.listMembers.mockResolvedValue([makeMember("a", "owner")]);
    await members.load("org");
    expect(members.members).toHaveLength(1);
    expect(members.loading).toBe(false);
  });

  it("invite() appends the created member", async () => {
    mocks.inviteMember.mockResolvedValue(makeMember("b", "member"));
    await members.invite("org", "b@example.com");
    expect(members.members.map((m) => m.id)).toContain("b");
  });

  it("changeRole() replaces the member by user_id", async () => {
    members.members = [makeMember("a", "member")];
    mocks.patchMemberRole.mockResolvedValue(makeMember("a", "admin"));
    await members.changeRole("org", "u-a", "admin");
    expect(members.members[0].role).toBe("admin");
  });

  it("remove() drops the member by user_id", async () => {
    members.members = [makeMember("a", "owner"), makeMember("b", "member")];
    mocks.removeMember.mockResolvedValue(undefined);
    await members.remove("org", "u-b");
    expect(members.members.map((m) => m.id)).toEqual(["a"]);
  });

  it("canManage is true for owner/admin and false for member", () => {
    members.myRole = "owner";
    expect(members.canManage).toBe(true);
    members.myRole = "admin";
    expect(members.canManage).toBe(true);
    members.myRole = "member";
    expect(members.canManage).toBe(false);
  });
});
