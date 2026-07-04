<script lang="ts">
  import { goto } from "$app/navigation";
  import { resolve } from "$app/paths";
  import { page } from "$app/state";
  import type { Pathname } from "$app/types";
  import * as Dialog from "$lib/components/ui/dialog";
  import { allNavItems, type NavContext } from "$lib/config/nav";
  import { commandPalette } from "$lib/stores/command-palette.svelte";
  import { shellMenus } from "$lib/stores/shell-menus.svelte";
  import { onboarding } from "$lib/stores/onboarding-store.svelte";
  import { pageTours } from "$lib/components/onboarding/tour-steps";
  import * as m from "$lib/paraglide/messages";

  // アプリ全体のキーボードショートカットを 1 か所で処理する（issue: ショートカット充実 Tier 1）。
  //   ⌘K / Ctrl+K … コマンドパレット開閉（入力中でも有効）
  //   /            … コマンドパレットを開く
  //   ?            … このショートカット一覧を表示
  //   g → 文字      … 現在プロジェクト配下へ移動（GitHub/Linear 流の 2 打鍵シーケンス）
  // モーダル/パレット/ツアーの Esc 閉じは bits-ui 各プリミティブが担うため個別実装は不要。

  const orgSlug = $derived(page.params.org ?? "");
  const projectSlug = $derived(page.params.project ?? "");
  const ctx = $derived<NavContext>({ orgSlug, projectSlug, projectSelected: !!page.params.project });

  // g シーケンスの遷移先（key → nav 項目 id）。ラベルは一覧ダイアログでも再利用する。
  const NAV_KEYS: { key: string; id: string; label: () => string }[] = [
    { key: "d", id: "overview", label: m.nav_overview },
    { key: "m", id: "galaxy", label: m.nav_galaxy },
    { key: "l", id: "knowledge-hub", label: m.nav_knowledge_hub },
    { key: "q", id: "matrix", label: m.nav_matrix },
    { key: "i", id: "repos", label: m.nav_repos },
    { key: "s", id: "settings", label: m.nav_settings },
  ];

  // ガイドを直接開く 2 打鍵（t → 文字）。ページ移動（g）と同じ 2 打鍵目キーで対応づける。
  // 対象は 5 つのみ（ダッシュボード / 理解度マップ / クイズと学習 / コード品質マップ / コード改善）。
  const GUIDE_KEYS = NAV_KEYS.filter((n) => pageTours[n.id]);

  // g / t を押した直後 1.2 秒だけ「2 打鍵目待ち」状態にする（Linear と同様のタイムアウト）。
  let gPending = false;
  let tPending = false;
  let gTimer: ReturnType<typeof setTimeout> | undefined;
  let tTimer: ReturnType<typeof setTimeout> | undefined;

  function resetG() {
    gPending = false;
    if (gTimer) clearTimeout(gTimer);
    gTimer = undefined;
  }
  function resetT() {
    tPending = false;
    if (tTimer) clearTimeout(tTimer);
    tTimer = undefined;
  }

  // 指定キーの詳細ガイドをトグル（プロジェクト選択時のみ。ガイドは各ページへ遷移してハイライトするため）。
  // 表示中に同じショートカット → 一時停止（非表示）。停止中に同じショートカット → 中断位置から再開。
  // 別のガイド/未起動なら新規開始。
  function openGuide(key: string) {
    if (!page.params.project) return;
    const g = GUIDE_KEYS.find((n) => n.key === key);
    const steps = g && pageTours[g.id];
    if (!g || !steps) return;
    if (onboarding.startKey === g.id) {
      if (onboarding.active) onboarding.pause();
      else onboarding.resume();
    } else {
      onboarding.start(steps, g.id);
    }
  }

  // 入力要素にフォーカス中はナビ系ショートカットを発火させない（検索窓での "/" 入力等を邪魔しない）。
  function isTyping(target: EventTarget | null): boolean {
    const el = target as HTMLElement | null;
    if (!el) return false;
    return el.isContentEditable || el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT";
  }

  function navigateTo(key: string) {
    if (key === "p") {
      // プロジェクト一覧（org ホーム）。プロジェクト未選択でも org があれば移動可。
      if (orgSlug) goto(resolve(`/${orgSlug}` as Pathname));
      return;
    }
    if (!orgSlug || !projectSlug) return;
    const target = NAV_KEYS.find((n) => n.key === key);
    const item = target && allNavItems.find((i) => i.id === target.id);
    if (item) goto(resolve(item.route(ctx)));
  }

  function onKeydown(e: KeyboardEvent) {
    // ⌘K / Ctrl+K はどこでも（入力中でも）パレットを開閉。
    if ((e.metaKey || e.ctrlKey) && !e.altKey && e.key.toLowerCase() === "k") {
      e.preventDefault();
      commandPalette.toggle();
      return;
    }
    // 以降は修飾キー無し・非入力時のみ。
    if (e.metaKey || e.ctrlKey || e.altKey || isTyping(e.target)) return;

    if (gPending) {
      const key = e.key.toLowerCase();
      resetG();
      if (key === "p" || NAV_KEYS.some((n) => n.key === key)) {
        e.preventDefault();
        navigateTo(key);
      }
      return;
    }

    if (tPending) {
      const key = e.key.toLowerCase();
      resetT();
      if (GUIDE_KEYS.some((n) => n.key === key)) {
        e.preventDefault();
        openGuide(key);
      }
      return;
    }

    if (e.key === "g") {
      gPending = true;
      gTimer = setTimeout(resetG, 1200);
      return;
    }

    if (e.key === "t") {
      tPending = true;
      tTimer = setTimeout(resetT, 1200);
      return;
    }
    if (e.key === "?") {
      e.preventDefault();
      shellMenus.shortcutList = true;
      return;
    }
    if (e.key === "/") {
      e.preventDefault();
      commandPalette.open = true;
    }
  }
</script>

<svelte:window onkeydown={onKeydown} />

{#snippet kbd(label: string)}
  <kbd
    class="inline-flex min-w-5 items-center justify-center rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-[10px] font-medium text-muted-foreground"
  >
    {label}
  </kbd>
{/snippet}

{#snippet row(label: string, keys: string[])}
  <li class="flex items-center justify-between gap-4">
    <span>{label}</span>
    <span class="flex shrink-0 items-center gap-1">
      {#each keys as k, i (i)}
        {#if k === "→"}
          <span class="text-muted-foreground">→</span>
        {:else}
          {@render kbd(k)}
        {/if}
      {/each}
    </span>
  </li>
{/snippet}

<Dialog.Root bind:open={shellMenus.shortcutList}>
  <Dialog.Content class="max-w-md" data-tour="shortcut-list">
    <Dialog.Header>
      <Dialog.Title>{m.shortcuts_title()}</Dialog.Title>
    </Dialog.Header>
    <div class="space-y-5 text-sm">
      <section>
        <h3 class="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          {m.shortcuts_section_general()}
        </h3>
        <ul class="space-y-2">
          {@render row(m.shell_command_palette(), ["⌘K", "/"])}
          {@render row(m.shortcuts_show_help(), ["?"])}
        </ul>
      </section>
      <section>
        <h3 class="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          {m.shortcuts_section_nav()}
        </h3>
        <ul class="space-y-2">
          {#each NAV_KEYS as n (n.key)}
            {@render row(n.label(), ["G", "→", n.key.toUpperCase()])}
          {/each}
          {@render row(m.project_home_title(), ["G", "→", "P"])}
        </ul>
      </section>
      <section>
        <h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
          {m.shortcuts_section_guides()}
        </h3>
        <ul class="space-y-2">
          {#each GUIDE_KEYS as n (n.key)}
            {@render row(n.label(), ["T", "→", n.key.toUpperCase()])}
          {/each}
        </ul>
      </section>
    </div>
  </Dialog.Content>
</Dialog.Root>
