<script lang="ts">
  import { Badge } from "$lib/components/ui/badge";
  import type { BadgeVariant } from "$lib/components/ui/badge";
  import type { OrgRole } from "$lib/api/schemas";
  import * as m from "$lib/paraglide/messages";

  let { role }: { role: OrgRole } = $props();

  const label: Record<OrgRole, string> = {
    owner: m.admin_members_role_owner(),
    admin: m.admin_members_role_admin(),
    member: m.admin_members_role_member(),
  };
  const variant: Record<OrgRole, BadgeVariant> = { owner: "default", admin: "secondary", member: "outline" };
</script>

<Badge variant={variant[role]}>{label[role]}</Badge>
