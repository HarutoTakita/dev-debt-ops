<script lang="ts">
  import CodeWalkthrough from "$lib/components/learning/code-walkthrough.svelte";
  import type { CodeDebt, CodeWalkthroughStep } from "$lib/api/schemas";
  import { categoryLabel, severityLabel } from "./labels";
  import * as m from "$lib/paraglide/messages";

  // コード改善（issue 210 の方針転換）: 修正 PR は作らず、該当コードを「このコードを理解する」と同じ
  // ウォークスルー UI（code-walkthrough）で行ハイライト表示し、なぜ品質が低いのかを説明する。
  // ソースは検知時に保存された抜粋（code_snippet）を使うため GitHub アクセス不要（ゲストデモでも動く）。
  const { debt }: { debt: CodeDebt } = $props();

  const content = $derived((debt.code_snippet ?? "").replace(/\n+$/, ""));
  const lineCount = $derived(content.length === 0 ? 1 : content.split("\n").length);
  // 1 ステップ = 該当抜粋の全行をハイライトし、検知根拠（なぜ品質が低いか）を解説する。
  const steps = $derived<CodeWalkthroughStep[]>([
    {
      start_line: 1,
      end_line: lineCount,
      title: `${categoryLabel(debt)}・${severityLabel(debt.severity)}`,
      explanation: debt.archaeology_notes || m.code_improve_no_reason(),
    },
  ]);
</script>

{#if content}
  <CodeWalkthrough {content} path={debt.file_path} {steps} />
{:else}
  <p class="rounded-lg border bg-card p-4 text-sm text-muted-foreground">{m.code_improve_no_snippet()}</p>
{/if}
