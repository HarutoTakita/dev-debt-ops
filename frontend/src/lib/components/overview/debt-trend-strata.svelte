<script lang="ts">
  import type { DebtTrendPoint } from "$lib/api/schemas";
  import * as m from "$lib/paraglide/messages";

  // 推移を「地層断面」として描く。各週を 1 層として積み、最新週を最上層に置く。
  // ダッシュボードは正の向き（コード品質 × 理解度）で統一。アンバーのバー = コード品質（= 1 - コード負債
  // スコア。週を追うごとに伸びる）、トラック（ティール）= 理解度の土台。
  type Props = { trend: DebtTrendPoint[] };
  const { trend }: Props = $props();

  const layers = $derived([...trend].reverse()); // 最新を最上層へ
  const pct = (v: number) => Math.round(Math.max(0, Math.min(1, v)) * 100);
  // week は保存時その解析の ISO タイムスタンプ（例 2026-06-24T11:53:…）。狭い列に収まるよう M/D HH:MM へ
  // 整形（日付のみは M/D、モックの "今週" 等はそのまま）。
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
        <span class="size-2 rounded-xs bg-debt-code/60"></span>{m.overview_trend_legend_debt()}
      </span>
      <span class="flex items-center gap-1">
        <span class="size-2 rounded-xs bg-debt-knowledge/40"></span>{m.overview_trend_legend_kc()}
      </span>
    </div>
  </div>

  {#if layers.length < 1}
    <!-- 解析が一度も実行されていないときだけ空状態を案内（解析ごとに 1 点記録、issue 067）。 -->
    <p class="mt-3 py-6 text-center text-xs leading-relaxed text-muted-foreground">{m.overview_trend_empty()}</p>
  {:else}
    <div class="mt-3 space-y-1">
      {#each layers as p (p.week)}
        <div class="flex items-center gap-2 text-xs">
          <span class="w-20 shrink-0 text-right whitespace-nowrap text-muted-foreground">{weekLabel(p.week)}</span>
          <div class="relative h-4 flex-1 overflow-hidden rounded-sm bg-debt-knowledge/15">
            <div
              class="absolute inset-y-0 left-0 bg-debt-code/55"
              style="width: {100 - pct(p.code_debt_score)}%"
            ></div>
          </div>
          <span class="w-32 shrink-0 text-right text-muted-foreground tabular-nums">
            {m.overview_trend_legend_debt()}
            {100 - pct(p.code_debt_score)} / {m.overview_trend_legend_kc()}
            {pct(p.knowledge_coverage)}
          </span>
        </div>
      {/each}
    </div>
  {/if}
</div>
