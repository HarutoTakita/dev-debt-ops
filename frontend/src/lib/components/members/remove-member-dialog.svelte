<script lang="ts">
  import Trash2 from "@lucide/svelte/icons/trash-2";
  import { toast } from "svelte-sonner";
  import * as Dialog from "$lib/components/ui/dialog";
  import { Button } from "$lib/components/ui/button";
  import { members } from "$lib/stores/members-store.svelte";
  import type { OrgMember } from "$lib/api/schemas";
  import * as m from "$lib/paraglide/messages";

  let { member, orgSlug }: { member: OrgMember; orgSlug: string } = $props();
  let open = $state(false);

  async function confirm() {
    try {
      await members.remove(orgSlug, member.user_id);
      open = false;
    } catch (e) {
      // 最後の owner 削除など API 422 をトーストで明示
      toast.error(e instanceof Error ? e.message : m.admin_members_remove_failed());
    }
  }
</script>

<Dialog.Root bind:open>
  <Dialog.Trigger>
    {#snippet child({ props })}
      <Button {...props} variant="ghost" size="icon-sm" aria-label={m.admin_members_remove_aria()}>
        <Trash2 class="size-4" />
      </Button>
    {/snippet}
  </Dialog.Trigger>
  <Dialog.Content>
    <Dialog.Header>
      <Dialog.Title>{m.admin_members_remove_title()}</Dialog.Title>
      <Dialog.Description>{member.user.display_name ?? member.user.email}</Dialog.Description>
    </Dialog.Header>
    <Dialog.Footer>
      <Button variant="outline" onclick={() => (open = false)}>{m.common_cancel()}</Button>
      <Button variant="destructive" onclick={confirm}>{m.common_delete()}</Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>
