<script lang="ts">
  import { toast } from "svelte-sonner";
  import { Button } from "$lib/components/ui/button";
  import { Input } from "$lib/components/ui/input";
  import { members } from "$lib/stores/members-store.svelte";
  import * as m from "$lib/paraglide/messages";

  let { orgSlug }: { orgSlug: string } = $props();
  let email = $state("");
  let submitting = $state(false);

  function valid(v: string): boolean {
    return /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v.trim());
  }

  async function submit(e: Event) {
    e.preventDefault();
    if (!valid(email)) {
      toast.error(m.common_field_invalid());
      return;
    }
    submitting = true;
    try {
      await members.invite(orgSlug, email.trim());
      email = "";
    } catch (err) {
      toast.error(err instanceof Error ? err.message : m.admin_members_invite_failed());
    } finally {
      submitting = false;
    }
  }
</script>

<form onsubmit={submit} class="flex items-center gap-2">
  <Input type="email" bind:value={email} placeholder={m.admin_members_invite_placeholder()} class="max-w-xs" />
  <Button type="submit" disabled={submitting}>
    {submitting ? m.admin_members_invite_submitting() : m.admin_members_invite_submit()}
  </Button>
</form>
