<script lang="ts">
  import { onMount } from "svelte";
  import ArrowLeft from "@lucide/svelte/icons/arrow-left";
  import Loader from "@lucide/svelte/icons/loader-circle";
  import { resolve } from "$app/paths";
  import type { ResolvedPathname } from "$app/types";
  import { getFileContent } from "$lib/api/client";
  import { repo } from "$lib/stores/repo-store.svelte";
  import CodeWalkthrough from "$lib/components/learning/code-walkthrough.svelte";
  import * as m from "$lib/paraglide/messages";

  let { data } = $props();

  // writable $derived: クライアント遷移で data が変わると追従しつつ、生成後の再取得結果も保持できる。
  let wt = $derived(data.walkthrough);
  let content = $state<string | null>(null);
  let busy = $state(true);
  let error = $state(false);

  const backHref = $derived(
    data.planId
      ? ((resolve(`/${data.orgSlug}/${data.projectSlug}/learning`) + `?planId=${data.planId}`) as ResolvedPathname)
      : resolve(`/${data.orgSlug}/${data.projectSlug}/learning`),
  );

  onMount(async () => {
    try {
      // 0. インラインのソースを持つリソース（ゲストデモ等）は GitHub を読まずそのまま表示する。
      if (wt.content != null) {
        content = wt.content;
        return;
      }
      // 1. ウォークスルーは「解析」時に事前生成済み（issue 298）。オンデマンド生成はせず表示のみ。
      //    ソースを取得し、事前生成済みステップ（あれば）とともに表示する（Gemini は呼ばない）。
      const src = wt.source_ref;
      const connected = repo.connected;
      if (!src || !connected) throw new Error("source unavailable");
      const fc = await getFileContent(connected.owner, connected.name, src, connected.default_branch);
      if (fc.content === null) throw new Error("file content unavailable");
      content = fc.content;
    } catch {
      error = true;
    } finally {
      busy = false;
    }
  });
</script>

<svelte:head>
  <title>{wt.title} · DevDebtOps</title>
</svelte:head>

<div class="mx-auto flex max-w-6xl flex-col gap-3 p-4">
  <!-- 上部: 戻る + ファイルパス -->
  <div class="flex flex-wrap items-center gap-2">
    <a href={backHref} class="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
      <ArrowLeft class="size-4" />
      {m.walkthrough_back()}
    </a>
    {#if wt.source_ref}
      <span class="min-w-0 flex-1 truncate text-right font-mono text-sm font-medium">{wt.source_ref}</span>
    {/if}
  </div>

  <div>
    <h1 class="font-display text-lg font-semibold">{wt.title}</h1>
    {#if wt.summary}
      <p class="mt-1 text-xs leading-relaxed text-muted-foreground">{wt.summary}</p>
    {/if}
  </div>

  {#if busy}
    <div class="flex items-center justify-center gap-2 py-16 text-sm text-muted-foreground">
      <Loader class="size-4 animate-spin" />
      {m.walkthrough_generating()}
    </div>
  {:else if error || content === null}
    <p class="py-16 text-center text-sm text-muted-foreground">{m.walkthrough_error()}</p>
  {:else}
    <CodeWalkthrough {content} path={wt.source_ref ?? ""} steps={wt.steps} />
  {/if}
</div>
