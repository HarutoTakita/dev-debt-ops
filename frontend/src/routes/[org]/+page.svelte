<script lang="ts">
  import { page } from "$app/state";
  import { resolve } from "$app/paths";
  import ComingSoonPlaceholder from "$lib/components/shell/coming-soon-placeholder.svelte";
  import * as m from "$lib/paraglide/messages";

  const orgSlug = $derived(page.params.org ?? "");
</script>

<svelte:head>
  <title>{m.nav_overview()} · Rosetta</title>
</svelte:head>

<!-- Overview は仕様書 §6.1 の二軸負債マトリクス / 推移グラフ / 優先対応リストが入る場所（本体は別 issue）。
     リポジトリビューアは [org]/repos へ退避済み。ここでは Repos への導線のみ残す。 -->
<ComingSoonPlaceholder
  feature={m.nav_overview()}
  description={m.coming_overview_desc()}
  primaryHref={resolve(`/${orgSlug}/repos`)}
  primaryLabel={m.nav_repos()}
/>
