<script lang="ts">
  import { members } from "$lib/stores/members-store.svelte";
  import InviteMemberForm from "$lib/components/members/invite-member-form.svelte";
  import MemberList from "$lib/components/members/member-list.svelte";
  import * as m from "$lib/paraglide/messages";

  let { data } = $props();

  // load 由来の myRole を反映し、一覧を取得（権限ガードは canManage で出し分け）。
  $effect(() => {
    members.myRole = data.myRole;
    members.load(data.orgSlug);
  });
</script>

<svelte:head>
  <title>{m.admin_members_title()} · Rosetta</title>
</svelte:head>

<div class="space-y-4">
  {#if members.canManage}
    <InviteMemberForm orgSlug={data.orgSlug} />
  {/if}
  <MemberList orgSlug={data.orgSlug} />
</div>
