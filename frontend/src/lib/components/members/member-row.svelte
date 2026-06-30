<script lang="ts">
  import { toast } from "svelte-sonner";
  import * as Avatar from "$lib/components/ui/avatar";
  import { members } from "$lib/stores/members-store.svelte";
  import type { OrgMember, OrgRole } from "$lib/api/schemas";
  import MemberRoleBadge from "./member-role-badge.svelte";
  import MemberRoleDropdown from "./member-role-dropdown.svelte";
  import RemoveMemberDialog from "./remove-member-dialog.svelte";
  import * as m from "$lib/paraglide/messages";

  // 1 行: アバター + 表示名/email + ロール + アクション。
  let { member, orgSlug, canManage }: { member: OrgMember; orgSlug: string; canManage: boolean } = $props();

  const displayName = $derived(member.user.display_name ?? member.user.email);
  const initial = $derived(displayName.slice(0, 1).toUpperCase());

  async function changeRole(role: OrgRole) {
    try {
      await members.changeRole(orgSlug, member.user_id, role);
    } catch (e) {
      // 最後の owner 降格など API 422 をトーストで明示
      toast.error(e instanceof Error ? e.message : m.admin_members_update_role_failed());
    }
  }
</script>

<div class="flex items-center gap-3 border-t px-3 py-2.5 text-sm">
  <Avatar.Root class="size-8">
    <Avatar.Fallback class="bg-muted text-xs">{initial}</Avatar.Fallback>
  </Avatar.Root>
  <div class="min-w-0 flex-1">
    <div class="truncate font-medium">{displayName}</div>
    <div class="truncate text-xs text-muted-foreground">{member.user.email}</div>
  </div>
  <div class="w-28 shrink-0">
    {#if canManage}
      <MemberRoleDropdown role={member.role} onchange={changeRole} />
    {:else}
      <MemberRoleBadge role={member.role} />
    {/if}
  </div>
  <div class="w-10 shrink-0 text-right">
    {#if canManage}
      <RemoveMemberDialog {member} {orgSlug} />
    {/if}
  </div>
</div>
