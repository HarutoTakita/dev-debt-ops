<script lang="ts">
  import { resolve } from "$app/paths";
  import type { ResolvedPathname } from "$app/types";
  import type { FileDebt } from "$lib/api/schemas";
  import { cn } from "$lib/utils";
  import * as m from "$lib/paraglide/messages";
  import AxisLegend from "./axis-legend.svelte";

  // 一次ビュー: ファイルを「コード品質 × チーム理解度(KC)」の平面に置いた散布図。
  // 縦軸 = コード品質（上 = クリーン = code_debt_score 小）/ 横軸 = KC（右 = 皆理解）。§2.3 準拠。
  type Props = { orgSlug: string; projectSlug: string; files: FileDebt[] };
  const { orgSlug, projectSlug, files }: Props = $props();

  let hovered = $state<FileDebt | null>(null);

  const matrixHref = $derived(resolve(`/${orgSlug}/${projectSlug}/matrix`));
  const dangerHref = $derived(`${matrixHref}?cell=danger` as ResolvedPathname);

  // 最危険ゾーン（左下）: 汚い × 誰も理解していない。
  function isDanger(f: FileDebt): boolean {
    return f.code_debt_score > 0.5 && f.knowledge_coverage < 0.5;
  }
</script>

<div class="rounded-lg border bg-card p-4">
  <div class="flex items-center gap-1.5">
    <span class="text-sm font-medium">{m.overview_matrix_title()}</span>
    <AxisLegend />
  </div>

  <div class="mt-3 flex gap-2">
    <!-- 縦軸ラベル（コード品質 ↑） -->
    <div class="flex w-4 shrink-0 items-center justify-center">
      <span class="rotate-180 text-[10px] whitespace-nowrap text-muted-foreground [writing-mode:vertical-rl]">
        {m.overview_axis_quality()} ↑
      </span>
    </div>

    <div class="min-w-0 flex-1">
      <div class="relative aspect-[5/4] w-full overflow-hidden rounded-md border">
        <!-- 4 象限の背景 -->
        <div class="absolute inset-0 grid grid-cols-2 grid-rows-2">
          <div class="border-r border-b border-border/40 bg-debt-knowledge/5"></div>
          <div class="border-b border-border/40 bg-success/5"></div>
          <a
            href={dangerHref}
            title={m.overview_open_danger_matrix()}
            aria-label={m.overview_open_danger_matrix()}
            class="border-r border-border/40 bg-destructive/15 transition-colors hover:bg-destructive/25"
          ></a>
          <div class="bg-debt-code/5"></div>
        </div>

        <!-- 象限ラベル。危険と釣り合うよう他 3 つもコントラスト/太さを上げる（色のみ依存を避ける）。 -->
        <span
          class="pointer-events-none absolute top-1.5 left-1.5 max-w-[45%] text-[10px] leading-tight font-medium text-foreground/75"
        >
          {m.overview_quadrant_code_repay()}
        </span>
        <span class="pointer-events-none absolute top-1.5 right-1.5 text-[10px] font-medium text-foreground/75">
          {m.overview_quadrant_ideal()}
        </span>
        <span class="pointer-events-none absolute bottom-1.5 left-1.5 text-[10px] font-semibold text-destructive">
          {m.overview_quadrant_danger()}
        </span>
        <span class="pointer-events-none absolute right-1.5 bottom-1.5 text-[10px] font-medium text-foreground/75">
          {m.overview_quadrant_refactor()}
        </span>

        <!-- プロット件数チップ -->
        <span
          class="pointer-events-none absolute top-1.5 left-1/2 -translate-x-1/2 rounded-full bg-background/70 px-1.5 text-[10px] text-muted-foreground tabular-nums"
        >
          {m.overview_scatter_count({ count: files.length })}
        </span>

        <!-- 点（ファイル）。left = KC, top = code_debt_score（汚いほど下）。危険点→/matrix?cell=danger、他→/matrix。
             大きさ + 塗り濃度（code_debt_score）+ 危険の '!' グリフで色のみ依存を避ける（rank10/20）。 -->
        {#each files as f (f.path)}
          <a
            href={isDanger(f) ? dangerHref : matrixHref}
            class={cn(
              "absolute flex -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full transition-transform before:absolute before:-inset-2 before:rounded-full before:content-['']",
              "hover:z-10 hover:scale-150 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none motion-reduce:hover:scale-100",
              isDanger(f) ? "size-4 bg-destructive ring-2 ring-destructive/25" : "size-3 bg-debt-knowledge",
            )}
            style="left: {f.knowledge_coverage * 100}%; top: {f.code_debt_score * 100}%;"
            style:opacity={isDanger(f) ? 1 : 0.45 + f.code_debt_score * 0.55}
            onmouseenter={() => (hovered = f)}
            onmouseleave={() => (hovered = null)}
            onfocus={() => (hovered = f)}
            onblur={() => (hovered = null)}
            title={isDanger(f) ? m.overview_open_danger_matrix() : f.path}
            aria-label={f.path}
          >
            {#if isDanger(f)}
              <span class="text-destructive-foreground pointer-events-none text-[9px] leading-none font-bold">!</span>
            {/if}
          </a>
        {/each}

        <!-- ホバーツールチップ -->
        {#if hovered}
          <div
            class="pointer-events-none absolute z-20 max-w-[80%] -translate-x-1/2 -translate-y-full rounded-md bg-foreground px-2 py-1 text-[10px] whitespace-nowrap text-background"
            style="left: {hovered.knowledge_coverage * 100}%; top: calc({hovered.code_debt_score * 100}% - 6px);"
          >
            <span class="font-mono">{hovered.path}</span>
            <span class="opacity-80">
              · {m.overview_tooltip_quality_kc({
                quality: Math.round((1 - hovered.code_debt_score) * 100),
                kc: Math.round(hovered.knowledge_coverage * 100),
              })}
            </span>
          </div>
        {/if}
      </div>

      <!-- 横軸ラベル（チーム理解度 →） -->
      <div class="mt-1 text-center text-[10px] text-muted-foreground">{m.overview_axis_kc()} →</div>
    </div>
  </div>
</div>
