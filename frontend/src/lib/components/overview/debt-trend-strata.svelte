<script lang="ts">
  import type { DebtTrendPoint } from "$lib/api/schemas";
  import * as m from "$lib/paraglide/messages";

  // コード品質（= 1 - コード負債スコア）と理解度（knowledge_coverage）の時系列を、スナップショットごとに
  // 2 本の縦棒（コード品質 / 理解度）で並べたグループ化棒グラフ。左→右が時系列、棒が高いほど良い（issue 067）。
  type Props = { trend: DebtTrendPoint[] };
  const { trend }: Props = $props();

  const pct = (v: number) => Math.round(Math.max(0, Math.min(1, v)) * 100);
  const quality = (p: DebtTrendPoint) => 100 - pct(p.code_debt_score); // コード品質 = 1 - コード負債スコア
  // week は解析ごとの ISO タイムスタンプ（例 2026-06-24T11:53:…）。M/D HH:MM へ整形（日付のみは M/D、モック等はそのまま）。
  function weekLabel(w: string): string {
    const t = w.match(/^\d{4}-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
    if (t) return `${+t[1]}/${+t[2]} ${t[3]}:${t[4]}`;
    const d = w.match(/^\d{4}-(\d{2})-(\d{2})$/);
    if (d) return `${+d[1]}/${+d[2]}`;
    return w;
  }
</script>

<div>
  <div class="flex items-center justify-between">
    <span class="text-sm font-medium">{m.overview_trend_title()}</span>
    <div class="flex gap-3 text-[10px] text-muted-foreground">
      <span class="flex items-center gap-1">
        <span class="size-2 rounded-xs bg-debt-code"></span>{m.overview_trend_legend_debt()}
      </span>
      <span class="flex items-center gap-1">
        <span class="size-2 rounded-xs bg-debt-knowledge"></span>{m.overview_trend_legend_kc()}
      </span>
    </div>
  </div>

  {#if trend.length < 1}
    <!-- 解析が一度も実行されていないときだけ空状態を案内（解析ごとに 1 点記録、issue 067）。 -->
    <p class="mt-3 py-6 text-center text-xs leading-relaxed text-muted-foreground">{m.overview_trend_empty()}</p>
  {:else}
    <p class="mt-0.5 text-[10px] text-muted-foreground">{m.overview_trend_hint()}</p>
    <!-- グループ化縦棒グラフ: スナップショットごとにコード品質 / 理解度の 2 本。左→右が時系列、高いほど良い。 -->
    <div class="mt-2 flex gap-2">
      <!-- 縦軸ラベル（0〜100% の割合） -->
      <div
        class="flex h-40 w-7 shrink-0 flex-col justify-between text-right text-[9px] text-muted-foreground tabular-nums"
      >
        <span>100%</span>
        <span>50%</span>
        <span>0%</span>
      </div>
      <div class="min-w-0 flex-1">
        <div class="relative h-40">
          <!-- 100% / 50% の目安線（縦軸スケール） -->
          <div class="pointer-events-none absolute inset-x-0 top-0 border-t border-border/40"></div>
          <div class="pointer-events-none absolute inset-x-0 top-1/2 border-t border-dashed border-border/50"></div>
          <div class="flex h-full items-end gap-1.5 border-b border-border">
            {#each trend as p (p.week)}
              <div class="flex h-full min-w-0 flex-1 items-end justify-center gap-1">
                <div
                  class="w-3.5 rounded-t bg-debt-code"
                  style="height: {quality(p)}%"
                  title="{m.overview_trend_legend_debt()} {quality(p)}%（{weekLabel(p.week)}）"
                ></div>
                <div
                  class="w-3.5 rounded-t bg-debt-knowledge"
                  style="height: {pct(p.knowledge_coverage)}%"
                  title="{m.overview_trend_legend_kc()} {pct(p.knowledge_coverage)}%（{weekLabel(p.week)}）"
                ></div>
              </div>
            {/each}
          </div>
        </div>
        <!-- x 軸ラベル（解析時刻） -->
        <div class="mt-1 flex gap-1.5">
          {#each trend as p (p.week)}
            <span class="min-w-0 flex-1 truncate text-center text-[9px] text-muted-foreground"
              >{weekLabel(p.week)}</span
            >
          {/each}
        </div>
      </div>
    </div>
  {/if}
</div>
