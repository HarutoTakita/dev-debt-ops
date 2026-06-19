<script lang="ts">
  import ChevronDown from "@lucide/svelte/icons/chevron-down";
  import * as DropdownMenu from "$lib/components/ui/dropdown-menu";
  import { Button } from "$lib/components/ui/button";
  import type { OrgRole } from "$lib/api/schemas";
  import * as m from "$lib/paraglide/messages";

  // canManage 時のみロール変更（owner / admin / member の PATCH）。
  let {
    role,
    disabled = false,
    onchange,
  }: { role: OrgRole; disabled?: boolean; onchange: (r: OrgRole) => void } = $props();

  const roles: OrgRole[] = ["owner", "admin", "member"];
  const label: Record<OrgRole, string> = {
    owner: m.admin_members_role_owner(),
    admin: m.admin_members_role_admin(),
    member: m.admin_members_role_member(),
  };
</script>

<DropdownMenu.Root>
  <DropdownMenu.Trigger {disabled}>
    {#snippet child({ props })}
      <Button {...props} variant="outline" size="sm" class="gap-1" {disabled}>
        {label[role]}
        <ChevronDown class="size-3.5" />
      </Button>
    {/snippet}
  </DropdownMenu.Trigger>
  <DropdownMenu.Content align="end">
    {#each roles as r (r)}
      <DropdownMenu.Item onSelect={() => onchange(r)}>{label[r]}</DropdownMenu.Item>
    {/each}
  </DropdownMenu.Content>
</DropdownMenu.Root>
