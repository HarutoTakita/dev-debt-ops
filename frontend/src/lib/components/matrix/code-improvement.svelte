<script lang="ts">
  import LoaderCircle from "@lucide/svelte/icons/loader-circle";
  import type { CodeDebt } from "$lib/api/schemas";
  import { getFileContent } from "$lib/api/client";
  import { repo } from "$lib/stores/repo-store.svelte";
  import CodeLines from "$lib/components/learning/code-lines.svelte";
  import DebtMetaPanel from "./debt-meta-panel.svelte";
  import * as m from "$lib/paraglide/messages";

  // コード改善（issue 210/227/231）: 左に該当コード、右に「品質が低い理由」+ メタ情報を縦 2 ブロック。
  // 表示は「ファイル全文 + 検知箇所のハイライト常時」。全文は getFileContent で取得し、検知時の抜粋
  // （code_snippet = ファイル先頭の連続抜粋）を全文内で特定して該当行をハイライトする。
  // 取得中はローディング表示にして、抜粋を一瞬見せてから全文に差し替わるチラつきを避け、初めから全文を出す。
  // 未接続（ゲストデモ）/ 取得失敗 / 抜粋を特定できない場合は抜粋表示にフォールバック（GitHub 不要）。
  const { debt }: { debt: CodeDebt } = $props();

  const snippet = $derived((debt.code_snippet ?? "").replace(/\n+$/, ""));
  const snippetLines = $derived(snippet.length === 0 ? 0 : snippet.split("\n").length);

  let viewContent = $state("");
  let hlStart = $state(0);
  let hlEnd = $state(0);
  let loading = $state(false);

  function showSnippet(snip: string, lines: number) {
    viewContent = snip;
    hlStart = snip ? 1 : 0;
    hlEnd = lines;
    loading = false;
  }

  $effect(() => {
    const connected = repo.connected;
    const path = debt.file_path;
    const snip = snippet;
    const lines = snippetLines;
    // 未接続（デモ）/ 抜粋なし: 即座に抜粋表示（ローディングなし）。
    if (!connected || !snip) {
      showSnippet(snip, lines);
      return;
    }
    // 接続あり: 全文取得を「読み込み中」表示で待ち、完了後に初めから全文を描画する（抜粋のチラ見せをしない）。
    loading = true;
    let cancelled = false;
    void getFileContent(connected.owner, connected.name, path, repo.selectedBranch || connected.default_branch)
      .then((file) => {
        if (cancelled) return;
        const full = (file.content ?? "").replace(/\n+$/, "");
        const idx = full.indexOf(snip);
        if (full && idx >= 0) {
          viewContent = full;
          hlStart = full.slice(0, idx).split("\n").length; // 抜粋開始行（1 始まり）
          hlEnd = hlStart + lines - 1;
          loading = false;
        } else {
          showSnippet(snip, lines); // 抜粋を全文内で特定できない（ファイル変化等）→ 抜粋表示
        }
      })
      .catch(() => {
        if (!cancelled) showSnippet(snip, lines); // 取得失敗（デモ/権限/ネットワーク）→ 抜粋表示
      });
    return () => {
      cancelled = true;
    };
  });
</script>

<div class="grid gap-4 lg:grid-cols-[1.7fr_1fr] lg:items-start" data-tour="debt-improve">
  <!-- 左: ファイル全文（検知箇所を常時ハイライト）。取得中はローディング表示。 -->
  {#if loading}
    <div
      class="flex max-h-[72vh] min-h-48 items-center justify-center gap-2 rounded-lg border bg-card text-sm text-muted-foreground"
    >
      <LoaderCircle class="size-4 animate-spin" />
      {m.common_loading()}
    </div>
  {:else if viewContent}
    <CodeLines content={viewContent} path={debt.file_path} highlightStart={hlStart} highlightEnd={hlEnd} />
  {:else}
    <p class="rounded-lg border bg-card p-4 text-sm text-muted-foreground">{m.code_improve_no_snippet()}</p>
  {/if}

  <!-- 右: 「品質が低い理由」+ メタ情報を縦に 2 ブロック（ローディング中も即表示してレイアウトを安定させる） -->
  <div class="flex flex-col gap-4">
    <div class="rounded-lg border bg-card p-4">
      <h3 class="font-display text-sm font-semibold text-debt-knowledge">{m.code_improve_why_heading()}</h3>
      <p class="mt-1.5 text-sm leading-relaxed">{debt.archaeology_notes || m.code_improve_no_reason()}</p>
    </div>
    <DebtMetaPanel {debt} showKc={false} />
  </div>
</div>
