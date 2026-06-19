import { inviteMember, listMembers, patchMemberRole, removeMember } from "$lib/api/client";
import type { OrgMember, OrgRole } from "$lib/api/schemas";

// org メンバー管理ストア（既存 API の配線）。Svelte 5 クラスベース runes。
class MembersStore {
  members = $state<OrgMember[]>([]);
  myRole = $state<OrgRole | null>(null);
  loading = $state(false);

  // owner / admin のみ編集系 UI を有効化
  canManage = $derived(this.myRole === "owner" || this.myRole === "admin");

  async load(orgSlug: string) {
    this.loading = true;
    try {
      this.members = await listMembers(orgSlug);
    } finally {
      this.loading = false;
    }
  }

  async invite(orgSlug: string, email: string) {
    const created = await inviteMember(orgSlug, email);
    this.members = [...this.members, created];
  }

  async changeRole(orgSlug: string, userId: string, role: OrgRole) {
    const updated = await patchMemberRole(orgSlug, userId, role);
    this.members = this.members.map((m) => (m.user_id === userId ? updated : m));
  }

  async remove(orgSlug: string, userId: string) {
    await removeMember(orgSlug, userId);
    this.members = this.members.filter((m) => m.user_id !== userId);
  }
}

export const members = new MembersStore();
