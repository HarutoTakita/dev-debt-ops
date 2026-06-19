<script lang="ts">
  import { members } from "$lib/stores/members-store.svelte";
  import MemberRow from "./member-row.svelte";
  import * as m from "$lib/paraglide/messages";

  let { orgSlug }: { orgSlug: string } = $props();
</script>

<div class="rounded-lg border bg-card">
  <div class="px-3 py-2 text-sm font-medium">
    {m.admin_members_title()} ({members.members.length})
  </div>
  {#if members.loading}
    <p class="border-t px-3 py-8 text-center text-sm text-muted-foreground">{m.admin_members_loading()}</p>
  {:else if members.members.length === 0}
    <p class="border-t px-3 py-8 text-center text-sm text-muted-foreground">{m.admin_members_empty()}</p>
  {:else}
    {#each members.members as member (member.id)}
      <MemberRow {member} {orgSlug} canManage={members.canManage} />
    {/each}
  {/if}
</div>
