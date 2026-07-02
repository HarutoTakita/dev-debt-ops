<script lang="ts">
  import { goto } from "$app/navigation";
  import { resolve } from "$app/paths";
  import { page } from "$app/state";
  import { onboarding } from "$lib/stores/onboarding-store.svelte";
  import { pageTours, type TourPlacement } from "./tour-steps";
  import * as m from "$lib/paraglide/messages";

  // 自作の軽量プロダクトツアー（issue 066）。外部 CDN/ライブラリ非依存。
  // data-tour 属性で対象要素を特定し、背景を暗転しつつ対象矩形を切り抜きハイライト、近傍に吹き出しを出す。
  // route 指定のステップは表示前に goto し、対象出現をポーリングで待つ。

  const orgSlug = $derived(page.params.org ?? "");
  const projectSlug = $derived(page.params.project ?? "");
  const total = $derived(onboarding.steps.length);
  const step = $derived(onboarding.active ? (onboarding.steps[onboarding.stepIndex] ?? null) : null);
  const isLast = $derived(onboarding.stepIndex >= onboarding.steps.length - 1);
  // メイン手順で、対応するページ別ガイドがあるステップだけ「詳細を確認する」を出す。
  const hasDetail = $derived(step ? Boolean(pageTours[step.id]) : false);

  type Rect = { x: number; y: number; w: number; h: number };
  let rect = $state<Rect | null>(null);

  function measure(target: string) {
    const el = document.querySelector(`[data-tour="${target}"]`);
    const r = el?.getBoundingClientRect();
    // 要素が無い / 非表示（0 サイズ）/ レイアウト未確定なら中央表示にフォールバック（変な位置を防ぐ）。
    if (!r || r.width === 0 || r.height === 0) {
      rect = null;
      return;
    }
    rect = { x: r.left, y: r.top, w: r.width, h: r.height };
  }

  // 対象がビューポート内に収まっているか（下方で見切れている等を検出）。
  function inViewport(r: DOMRect): boolean {
    return r.top >= 0 && r.left >= 0 && r.bottom <= window.innerHeight && r.right <= window.innerWidth;
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
        // route（パス）＋ 任意の search（クエリ, 例: ?path=… でファイルを事前選択）へ遷移。クエリ差分も
        // 検知するため pathname だけでなく search も含めて現在地と比較する。
        const target =
          resolve(s.route({ orgSlug, projectSlug })) + (s.search ? s.search({ orgSlug, projectSlug }) : "");
        if (page.url.pathname + page.url.search !== target) {
          // target は resolve 済みパス＋クエリ文字列。resolve はクエリを扱えないため連結しており、
          // svelte/no-navigation-without-resolve は無効化する（パス部分は resolve 済み）。
          // eslint-disable-next-line svelte/no-navigation-without-resolve
          await goto(target);
        }
      }
      // タブ等の隠れた対象は、表示前に reveal 要素をクリックして出す（例: マップ/リスト切替、詳細画面への遷移）。
      if (s.reveal) {
        const rev = document.querySelector<HTMLElement>(`[data-tour="${s.reveal}"]`);
        rev?.click();
        // reveal がリンク（クライアント遷移）の場合、遷移完了までわずかに待ってから対象を探す。
        await new Promise((r) => setTimeout(r, 120));
      }
      if (!s.target) {
        rect = null; // ターゲット無し（ページ別ガイドの詳細）は中央に説明だけ出す
        return;
      }
      const target = s.target;
      // 遷移直後・レイアウト確定前を考慮し、可視（サイズあり）になるまで待つ（最大 ~2s）。
      // 出現しなければ measure() が中央フォールバックする（変な位置に出さない）。
      let el: Element | null = null;
      for (let i = 0; i < 40 && !cancelled; i++) {
        el = document.querySelector(`[data-tour="${target}"]`);
        if (el && el.getBoundingClientRect().width > 0) break;
        await new Promise((r) => setTimeout(r, 50));
      }
      if (cancelled) return;
      // 対象が画面外（下方で見切れている等）ならビューポート中央へスクロールしてから計測する。
      // （スクロール中も scroll リスナーが再計測するので、ハイライトと吹き出しは追従する。）
      const r0 = el?.getBoundingClientRect();
      if (el && r0 && !inViewport(r0)) {
        el.scrollIntoView({ block: "center", behavior: "smooth" });
        await new Promise((r) => setTimeout(r, 300));
      }
      if (!cancelled) measure(target);
    })();
    return () => {
      cancelled = true;
    };
  });

  // resize / scroll で再計測（実行中のみ）。
  $effect(() => {
    if (!onboarding.active || !step || !step.target) return;
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

  const PAD = 6; // ハイライトの外周パディング（切り抜き ring と揃える）
  const GAP = 12; // ハイライトと吹き出しの間隔
  const MARGIN = 8; // ビューポート端の最小マージン
  const BUBBLE_W = 320;
  // 吹き出しの実測サイズ（bind:clientWidth/Height）。文言量で高さが変わるため実測し、ハイライトへの
  // 被りを防ぐ。未計測時は既定値でフォールバック。
  let bubbleW = $state(BUBBLE_W);
  let bubbleH = $state(180);

  // 吹き出し位置。ハイライト矩形に**重ならない**配置を選ぶ（従来はブロック高を 160px 固定で仮定し、端では
  // ビューポートクランプがハイライト上へ押し戻していた）。優先 placement → 反対側 → 上下左右の順に、
  // 「主軸は対象の外側・交差軸はビューポート内」に収まる側を採用。どこにも収まらない（対象が大きすぎる）
  // 場合は、最も余白のある側のビューポート端に寄せて被りを最小化する。rect 無しは中央。
  const bubble = $derived.by(() => {
    if (!rect) return { left: -9999, top: -9999, centered: true };
    const r = rect;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const W = bubbleW || BUBBLE_W;
    const H = bubbleH || 180;
    const clampX = (x: number) => Math.max(MARGIN, Math.min(x, vw - W - MARGIN));
    const clampY = (y: number) => Math.max(MARGIN, Math.min(y, vh - H - MARGIN));
    // 各サイドの候補（主軸=対象の外側に固定、交差軸のみビューポートへクランプ）。
    const cand: Record<TourPlacement, { left: number; top: number }> = {
      bottom: { left: clampX(r.x), top: r.y + r.h + PAD + GAP },
      top: { left: clampX(r.x), top: r.y - PAD - GAP - H },
      right: { left: r.x + r.w + PAD + GAP, top: clampY(r.y) },
      left: { left: r.x - PAD - GAP - W, top: clampY(r.y) },
    };
    const fits = (c: { left: number; top: number }) =>
      c.left >= MARGIN && c.top >= MARGIN && c.left + W <= vw - MARGIN && c.top + H <= vh - MARGIN;
    const opposite: Record<TourPlacement, TourPlacement> = {
      bottom: "top",
      top: "bottom",
      left: "right",
      right: "left",
    };
    const preferred = step?.placement ?? "right";
    const order: TourPlacement[] = [preferred, opposite[preferred], "bottom", "top", "right", "left"];
    for (const side of order) {
      if (fits(cand[side])) return { ...cand[side], centered: false };
    }
    // フォールバック: どの側も収まらない（対象がほぼ全画面など）→ 最も余白のある側の端に寄せる。
    const space: Record<TourPlacement, number> = {
      bottom: vh - (r.y + r.h),
      top: r.y,
      right: vw - (r.x + r.w),
      left: r.x,
    };
    const best = order.reduce((a, b) => (space[b] > space[a] ? b : a));
    const edge: Record<TourPlacement, { left: number; top: number }> = {
      bottom: { left: clampX(r.x), top: vh - H - MARGIN },
      top: { left: clampX(r.x), top: MARGIN },
      right: { left: vw - W - MARGIN, top: clampY(r.y) },
      left: { left: MARGIN, top: clampY(r.y) },
    };
    return { ...edge[best], centered: false };
  });

  function onNext() {
    if (!isLast) {
      onboarding.next();
    } else if (onboarding.inDetail) {
      onboarding.backToMain(); // ページ別ガイドの最後 → 全体ガイドの元の位置へ戻る
    } else {
      onboarding.finish(orgSlug);
    }
  }

  // 「詳細を確認する」: 当該メニューのページ別ガイドに切り替える（全体ガイドの位置は保持）。
  function openDetail() {
    if (!step) return;
    const pt = pageTours[step.id];
    if (pt) onboarding.startDetail(pt);
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

  <!-- 吹き出し（実測サイズで被り回避の配置計算に使う） -->
  <div
    role="dialog"
    aria-modal="true"
    aria-label={step.title()}
    bind:clientWidth={bubbleW}
    bind:clientHeight={bubbleH}
    class="fixed z-[201] w-[320px] rounded-lg border bg-card p-4 shadow-xl"
    style={bubble.centered
      ? "left: 50%; top: 50%; transform: translate(-50%, -50%);"
      : `left: ${bubble.left}px; top: ${bubble.top}px;`}
  >
    {#if onboarding.inDetail}
      <button
        type="button"
        onclick={() => onboarding.backToMain()}
        class="mb-1 text-xs font-medium whitespace-nowrap text-muted-foreground hover:text-foreground"
      >
        ← {m.tour_back_to_main()}
      </button>
    {/if}
    <p class="font-display text-sm font-semibold">{step.title()}</p>
    <p class="mt-1 text-sm leading-relaxed text-muted-foreground">{step.body()}</p>
    {#if hasDetail}
      <button type="button" onclick={openDetail} class="mt-2 text-xs font-medium text-primary hover:underline">
        {m.tour_detail()} →
      </button>
    {/if}
    <div class="mt-3 flex flex-wrap items-center justify-between gap-2">
      <span class="text-xs text-muted-foreground tabular-nums">{onboarding.stepIndex + 1} / {total}</span>
      <div class="flex flex-wrap items-center gap-1.5">
        <button
          type="button"
          onclick={() => onboarding.finish(orgSlug)}
          class="rounded-md px-2 py-1 text-xs whitespace-nowrap text-muted-foreground hover:text-foreground"
        >
          {m.tour_skip()}
        </button>
        {#if onboarding.stepIndex > 0}
          <button
            type="button"
            onclick={() => onboarding.prev()}
            class="rounded-md border px-2.5 py-1 text-xs font-medium whitespace-nowrap hover:bg-accent/40"
          >
            {m.tour_prev()}
          </button>
        {/if}
        <button
          type="button"
          onclick={onNext}
          class="rounded-md bg-primary px-2.5 py-1 text-xs font-medium whitespace-nowrap text-primary-foreground hover:bg-primary/90"
        >
          {isLast ? (onboarding.inDetail ? m.tour_back_to_main() : m.tour_finish()) : m.tour_next()}
        </button>
      </div>
    </div>
  </div>
{/if}
