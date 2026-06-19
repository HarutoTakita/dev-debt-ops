import { describe, expect, it } from "vitest";
import { page } from "@vitest/browser/context";
import { render } from "vitest-browser-svelte";
import MemberRow from "./member-row.svelte";
import type { OrgMember } from "$lib/api/schemas";

const member: OrgMember = {
  id: "1",
  user_id: "u1",
  org_id: "o",
  role: "member",
  created_at: "2026-01-01T00:00:00+09:00",
  user: { id: "u1", email: "bob@example.com", display_name: "bob", is_active: true },
};

describe("MemberRow", () => {
  it("renders display name and role label", async () => {
    render(MemberRow, { member, orgSlug: "org", canManage: false });
    await expect.element(page.getByText("bob", { exact: true })).toBeInTheDocument();
    await expect.element(page.getByText("メンバー")).toBeInTheDocument();
  });

  it("hides the remove action when canManage is false", async () => {
    const { container } = render(MemberRow, { member, orgSlug: "org", canManage: false });
    await expect.element(page.getByText("bob@example.com")).toBeInTheDocument();
    expect(container.querySelector('[aria-label="メンバーを削除"]')).toBeNull();
  });

  it("shows the remove action when canManage is true", async () => {
    render(MemberRow, { member, orgSlug: "org", canManage: true });
    await expect.element(page.getByRole("button", { name: "メンバーを削除" })).toBeInTheDocument();
  });
});
