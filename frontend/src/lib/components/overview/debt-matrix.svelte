<script lang="ts">
  import ArrowUp from "@lucide/svelte/icons/arrow-up";
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
  // ツールチップの表示位置: ホバー中アイコンの画面座標（中心 x / 上端 y）。fixed で描画して
  // マトリクスの overflow-hidden 枠に切られないようにし、アイコンの真上に出す。
  let anchor = $state<{ cx: number; top: number } | null>(null);
  let tipW = $state(0); // ツールチップ実測幅（左右クランプに使う）

  function showTip(f: FileDebt, e: Event) {
    hovered = f;
    const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
    anchor = { cx: r.left + r.width / 2, top: r.top };
  }
  function hideTip() {
    hovered = null;
    anchor = null;
  }

  // 画面端で途切れないよう、中心 x をビューポート内（左右 8px マージン＋ツールチップ半幅）にクランプ。
  const tipLeft = $derived.by(() => {
    if (!anchor) return 0;
    const margin = 8;
    const half = tipW / 2;
    const vw = typeof window !== "undefined" ? window.innerWidth : 0;
    const min = margin + half;
    const max = vw - margin - half;
    return max < min ? anchor.cx : Math.min(Math.max(anchor.cx, min), max);
  });

  const matrixHref = $derived(resolve(`/${orgSlug}/${projectSlug}/matrix`));
  const dangerHref = $derived(`${matrixHref}?cell=danger` as ResolvedPathname);

  // 最危険ゾーン（左下）: 汚い × 誰も理解していない。
  function isDanger(f: FileDebt): boolean {
    return f.code_debt_score > 0.5 && f.knowledge_coverage < 0.5;
  }

  // 0..1 のスコアをパーセント座標へ。両端に余白(PAD)を設け、KC/品質が 0 または 1 の点でもプロット枠の
  // 縁で見切れないよう内側へ寄せる（0→PAD%、0.5→50%、1→(100-PAD)%。象限境界の 50% は不変）。
  const PAD = 5;
  function pct(score: number): number {
    return PAD + Math.max(0, Math.min(1, score)) * (100 - 2 * PAD);
  }
</script>

<div class="flex h-full flex-col rounded-lg border bg-card p-4">
  <div class="flex items-center gap-1.5">
    <span class="text-sm font-medium">{m.overview_matrix_title()}</span>
    <AxisLegend />
  </div>

  <div class="mt-3 flex min-h-0 flex-1 gap-2">
    <!-- 縦軸ラベル（上＝コード品質が高い）。矢印は明示的な上向きアイコンで示す。 -->
    <div class="flex w-4 shrink-0 flex-col items-center justify-center gap-1 text-muted-foreground">
      <ArrowUp class="size-3" />
      <span class="text-[10px] whitespace-nowrap [writing-mode:vertical-rl]">
        {m.overview_axis_quality()}
      </span>
    </div>

    <div class="flex min-w-0 flex-1 flex-col">
      <!-- モバイル(単一カラムで grid セル高が auto)では flex-1 がつぶれるため min-h の下限を与える。
           lg 以上は行の高さ(h-full)に追従させるため min-h-0 に戻す。 -->
      <div class="relative min-h-[260px] w-full flex-1 overflow-hidden rounded-md border lg:min-h-0">
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
            style="left: {pct(f.knowledge_coverage)}%; top: {pct(f.code_debt_score)}%;"
            style:opacity={isDanger(f) ? 1 : 0.45 + Math.max(0, Math.min(1, f.code_debt_score)) * 0.55}
            onmouseenter={(e) => showTip(f, e)}
            onmouseleave={hideTip}
            onfocus={(e) => showTip(f, e)}
            onblur={hideTip}
            title={isDanger(f) ? m.overview_open_danger_matrix() : f.path}
            aria-label={f.path}
          >
            {#if isDanger(f)}
              <span class="text-destructive-foreground pointer-events-none text-[9px] leading-none font-bold">!</span>
            {/if}
          </a>
        {/each}
      </div>

      <!-- 横軸ラベル（チーム理解度 →） -->
      <div class="mt-1 text-center text-[10px] text-muted-foreground">{m.overview_axis_kc()} →</div>
    </div>
  </div>
</div>

<!-- 情報ツールチップ。fixed 描画でマトリクス枠に切られず、アイコンの真上に出す。左右はビューポート内にクランプ。 -->
{#if hovered && anchor}
  <div
    bind:clientWidth={tipW}
    class="pointer-events-none fixed z-50 max-w-[90vw] -translate-x-1/2 -translate-y-full rounded-md border border-border bg-foreground px-2.5 py-1 text-xs whitespace-nowrap text-background shadow-lg"
    style="left: {tipLeft}px; top: {anchor.top - 8}px;"
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
