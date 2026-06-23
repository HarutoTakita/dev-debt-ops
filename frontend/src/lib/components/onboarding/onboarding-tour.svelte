<script lang="ts">
  import { goto } from "$app/navigation";
  import { resolve } from "$app/paths";
  import { page } from "$app/state";
  import { onboarding } from "$lib/stores/onboarding-store.svelte";
  import { tourSteps } from "./tour-steps";
  import * as m from "$lib/paraglide/messages";

  // 自作の軽量プロダクトツアー（issue 066）。外部 CDN/ライブラリ非依存。
  // data-tour 属性で対象要素を特定し、背景を暗転しつつ対象矩形を切り抜きハイライト、近傍に吹き出しを出す。
  // route 指定のステップは表示前に goto し、対象出現をポーリングで待つ。

  const orgSlug = $derived(page.params.org ?? "");
  const projectSlug = $derived(page.params.project ?? "");
  const total = tourSteps.length;
  const step = $derived(onboarding.active ? (tourSteps[onboarding.stepIndex] ?? null) : null);
  const isLast = $derived(onboarding.stepIndex >= total - 1);

  type Rect = { x: number; y: number; w: number; h: number };
  let rect = $state<Rect | null>(null);

  function measure(target: string) {
    const el = document.querySelector(`[data-tour="${target}"]`);
    if (!el) {
      rect = null;
      return;
    }
    const r = el.getBoundingClientRect();
    rect = { x: r.left, y: r.top, w: r.width, h: r.height };
  }

  // ステップ変化: route 遷移 → 対象出現待ち → 計測。
  $effect(() => {
    const s = step;
    if (!s) {
      rect = null;
      return;
    }
    let cancelled = false;
    (async () => {
      if (s.route) {
        const href = s.route({ orgSlug, projectSlug });
        if (page.url.pathname !== href) await goto(resolve(href));
      }
      for (let i = 0; i < 40 && !cancelled; i++) {
        if (document.querySelector(`[data-tour="${s.target}"]`)) break;
        await new Promise((r) => setTimeout(r, 50));
      }
      if (!cancelled) measure(s.target);
    })();
    return () => {
      cancelled = true;
    };
  });

  // resize / scroll で再計測（実行中のみ）。
  $effect(() => {
    if (!onboarding.active || !step) return;
    const target = step.target;
    const recompute = () => measure(target);
    window.addEventListener("resize", recompute);
    window.addEventListener("scroll", recompute, true);
    return () => {
      window.removeEventListener("resize", recompute);
      window.removeEventListener("scroll", recompute, true);
    };
  });

  // Esc でスキップ。
  $effect(() => {
    if (!onboarding.active) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onboarding.finish(orgSlug);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const PAD = 6;
  const BUBBLE_W = 300;
  // 吹き出し位置（rect + placement から。ビューポート内にクランプ）。rect 無しは中央。
  const bubble = $derived.by(() => {
    if (!rect) return { left: -9999, top: -9999, centered: true };
    const r = rect;
    let left: number;
    let top: number;
    if (step?.placement === "bottom") {
      left = r.x;
      top = r.y + r.h + PAD + 6;
    } else if (step?.placement === "left") {
      left = r.x - BUBBLE_W - PAD - 6;
      top = r.y;
    } else if (step?.placement === "top") {
      left = r.x;
      top = r.y - PAD - 160;
    } else {
      // right（既定）
      left = r.x + r.w + PAD + 6;
      top = r.y;
    }
    left = Math.max(8, Math.min(left, window.innerWidth - BUBBLE_W - 8));
    top = Math.max(8, Math.min(top, window.innerHeight - 180));
    return { left, top, centered: false };
  });

  function onNext() {
    if (isLast) onboarding.finish(orgSlug);
    else onboarding.next();
  }
</script>

{#if onboarding.active && step}
  <!-- 背景。クリックはツアー外への誤操作を防ぐため吸収（何もしない）。 -->
  <div class="fixed inset-0 z-[200]" aria-hidden="true">
    {#if rect}
      <!-- 対象の切り抜きハイライト（外側を box-shadow で暗転）。 -->
      <div
        class="pointer-events-none fixed rounded-lg ring-2 ring-primary transition-all duration-150"
        style="left: {rect.x - PAD}px; top: {rect.y - PAD}px; width: {rect.w + PAD * 2}px; height: {rect.h +
          PAD * 2}px; box-shadow: 0 0 0 9999px rgba(2, 6, 23, 0.62);"
      ></div>
    {:else}
      <div class="fixed inset-0 bg-slate-950/60"></div>
    {/if}
  </div>

  <!-- 吹き出し -->
  <div
    role="dialog"
    aria-modal="true"
    aria-label={step.title()}
    class="fixed z-[201] w-[300px] rounded-lg border bg-card p-4 shadow-xl"
    style={bubble.centered
      ? "left: 50%; top: 50%; transform: translate(-50%, -50%);"
      : `left: ${bubble.left}px; top: ${bubble.top}px;`}
  >
    <p class="font-display text-sm font-semibold">{step.title()}</p>
    <p class="mt-1 text-sm leading-relaxed text-muted-foreground">{step.body()}</p>
    <div class="mt-3 flex items-center justify-between gap-2">
      <span class="text-xs text-muted-foreground tabular-nums">{onboarding.stepIndex + 1} / {total}</span>
      <div class="flex items-center gap-1.5">
        <button
          type="button"
          onclick={() => onboarding.finish(orgSlug)}
          class="rounded-md px-2 py-1 text-xs text-muted-foreground hover:text-foreground"
        >
          {m.tour_skip()}
        </button>
        {#if onboarding.stepIndex > 0}
          <button
            type="button"
            onclick={() => onboarding.prev()}
            class="rounded-md border px-2.5 py-1 text-xs font-medium hover:bg-accent/40"
          >
            {m.tour_prev()}
          </button>
        {/if}
        <button
          type="button"
          onclick={onNext}
          class="rounded-md bg-primary px-2.5 py-1 text-xs font-medium text-primary-foreground hover:bg-primary/90"
        >
          {isLast ? m.tour_finish() : m.tour_next()}
        </button>
      </div>
    </div>
  </div>
{/if}
