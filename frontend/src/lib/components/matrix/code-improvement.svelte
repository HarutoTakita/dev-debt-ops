<script lang="ts">
  import type { CodeDebt } from "$lib/api/schemas";
  import CodeLines from "$lib/components/learning/code-lines.svelte";
  import DebtMetaPanel from "./debt-meta-panel.svelte";
  import * as m from "$lib/paraglide/messages";

  // コード改善（issue 210）: 左に該当コード（1 列・行ハイライト）、右に「品質が低い理由」と
  // メタ情報（深刻度 / 種別 / 修正工数 / 開発担当者。理解度 KC は出さない）を縦に 2 ブロック並べる。
  // ソースは検知時の抜粋（code_snippet）を使うため GitHub アクセス不要（ゲストデモでも動く）。
  const { debt }: { debt: CodeDebt } = $props();

  const content = $derived((debt.code_snippet ?? "").replace(/\n+$/, ""));
  const lineCount = $derived(content.length === 0 ? 0 : content.split("\n").length);
</script>

{#if content}
  <div class="grid gap-4 lg:grid-cols-[1.7fr_1fr] lg:items-start">
    <!-- 左: 該当コード（全行ハイライト） -->
    <CodeLines {content} path={debt.file_path} highlightStart={1} highlightEnd={lineCount} />

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
