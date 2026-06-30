<script lang="ts">
  import type { CodeDebt } from "$lib/api/schemas";
  import { getFileContent } from "$lib/api/client";
  import { repo } from "$lib/stores/repo-store.svelte";
  import CodeLines from "$lib/components/learning/code-lines.svelte";
  import DebtMetaPanel from "./debt-meta-panel.svelte";
  import * as m from "$lib/paraglide/messages";

  // コード改善（issue 210/227）: 左に該当コード、右に「品質が低い理由」+ メタ情報を縦 2 ブロック。
  // 表示は「ファイル全文 + 検知箇所のハイライト常時」。全文は getFileContent で取得し、検知時の抜粋
  // （code_snippet = ファイル先頭の連続抜粋）を全文内で特定して該当行をハイライトする。全文取得に失敗/
  // 未接続（ゲストデモ）/ 抜粋を特定できない場合は、従来どおり抜粋のみ表示にフォールバック（GitHub 不要）。
  const { debt }: { debt: CodeDebt } = $props();

  const snippet = $derived((debt.code_snippet ?? "").replace(/\n+$/, ""));
  const snippetLines = $derived(snippet.length === 0 ? 0 : snippet.split("\n").length);

  // 表示中のソースとハイライト範囲。既定は抜粋（全行ハイライト）。
  let viewContent = $state("");
  let hlStart = $state(0);
  let hlEnd = $state(0);

  // debt が変わるたび、まず抜粋表示で初期化（全文取得は後段の effect が成功時のみ差し替える）。
  $effect(() => {
    viewContent = snippet;
    hlStart = snippet ? 1 : 0;
    hlEnd = snippetLines;
  });

  // 全文取得 → 抜粋位置を特定できたら全文 + 該当行ハイライトに差し替え。失敗時は抜粋表示のまま。
  $effect(() => {
    const connected = repo.connected;
    const path = debt.file_path;
    const snip = snippet;
    if (!connected || !snip) return;
    let cancelled = false;
    void getFileContent(connected.owner, connected.name, path, repo.selectedBranch || connected.default_branch)
      .then((file) => {
        if (cancelled) return;
        const full = (file.content ?? "").replace(/\n+$/, "");
        const idx = full.indexOf(snip);
        if (!full || idx < 0) return; // 抜粋を全文内で特定できない（ファイル変化等）→ 抜粋表示のまま
        viewContent = full;
        hlStart = full.slice(0, idx).split("\n").length; // 抜粋開始行（1 始まり）
        hlEnd = hlStart + snippetLines - 1;
      })
      .catch(() => {
        /* デモ / 権限なし / ネットワーク等 → 抜粋表示のまま（フォールバック） */
      });
    return () => {
      cancelled = true;
    };
  });
</script>

{#if viewContent}
  <div class="grid gap-4 lg:grid-cols-[1.7fr_1fr] lg:items-start">
    <!-- 左: ファイル全文（検知箇所を常時ハイライト） -->
    <CodeLines content={viewContent} path={debt.file_path} highlightStart={hlStart} highlightEnd={hlEnd} />

    <!-- 右: 「品質が低い理由」+ メタ情報を縦に 2 ブロック -->
    <div class="flex flex-col gap-4">
      <div class="rounded-lg border bg-card p-4">
        <h3 class="font-display text-sm font-semibold text-debt-knowledge">{m.code_improve_why_heading()}</h3>
        <p class="mt-1.5 text-sm leading-relaxed">{debt.archaeology_notes || m.code_improve_no_reason()}</p>
      </div>
      <DebtMetaPanel {debt} showKc={false} />
    </div>
  </div>
{:else}
  <p class="rounded-lg border bg-card p-4 text-sm text-muted-foreground">{m.code_improve_no_snippet()}</p>
{/if}
