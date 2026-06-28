<script lang="ts">
  import { marked } from "marked";
  import * as Dialog from "$lib/components/ui/dialog";
  import * as m from "$lib/paraglide/messages";

  // 中央モーダルで CHANGELOG.md を Markdown ビューアとして表示する。
  // CHANGELOG は repo ルートが正本で、ビルド時に静的アセット `/CHANGELOG.md` として同梱される
  // （vite: `static/CHANGELOG.md` / Docker: frontend ステージで COPY）。初回オープン時に fetch する。
  let { open = $bindable(false) }: { open?: boolean } = $props();

  let html = $state("");
  let loading = $state(false);
  let error = $state(false);
  let loaded = false;

  async function load() {
    if (loaded) return;
    loading = true;
    error = false;
    try {
      const res = await fetch("/CHANGELOG.md", { headers: { Accept: "text/markdown,text/plain" } });
      if (!res.ok) throw new Error(String(res.status));
      const text = await res.text();
      // CHANGELOG は repo 同梱の信頼済みコンテンツ（ユーザー入力ではない）。よって {@html} で描画する。
      html = await marked.parse(text);
      loaded = true;
    } catch {
      error = true;
    } finally {
      loading = false;
    }
  }

  $effect(() => {
    if (open) void load();
  });
</script>

<Dialog.Root bind:open>
  <Dialog.Content class="sm:max-w-2xl">
    <Dialog.Header>
      <Dialog.Title>{m.changelog_title()}</Dialog.Title>
      <Dialog.Description>v{__APP_VERSION__}</Dialog.Description>
    </Dialog.Header>

    <div class="max-h-[70vh] overflow-y-auto pr-1">
      {#if loading}
        <p class="py-8 text-center text-sm text-muted-foreground">{m.changelog_loading()}</p>
      {:else if error}
        <p class="py-8 text-center text-sm text-destructive">{m.changelog_error()}</p>
      {:else}
        <!-- eslint-disable-next-line svelte/no-at-html-tags -->
        <div class="changelog-md text-sm leading-relaxed">{@html html}</div>
      {/if}
    </div>
  </Dialog.Content>
</Dialog.Root>

<style>
  /* typography プラグイン非使用のため、Markdown の最低限の体裁を自前で付与する。 */
  .changelog-md :global(h1) {
    margin: 1rem 0 0.5rem;
    font-size: 1.125rem;
    font-weight: 700;
  }
  .changelog-md :global(h2) {
    margin: 1.25rem 0 0.5rem;
    border-bottom: 1px solid var(--border);
    padding-bottom: 0.25rem;
    font-size: 1rem;
    font-weight: 700;
  }
  .changelog-md :global(h3) {
    margin: 1rem 0 0.375rem;
    font-size: 0.9375rem;
    font-weight: 600;
  }
  .changelog-md :global(p) {
    margin: 0.5rem 0;
  }
  .changelog-md :global(ul),
  .changelog-md :global(ol) {
    margin: 0.375rem 0;
    padding-left: 1.25rem;
    list-style: disc;
  }
  .changelog-md :global(ol) {
    list-style: decimal;
  }
  .changelog-md :global(li) {
    margin: 0.125rem 0;
  }
  .changelog-md :global(a) {
    color: #2563eb; /* blue-600: ライトモードで読みやすい青 */
    text-decoration: underline;
  }
  :global(.dark) .changelog-md :global(a) {
    color: #60a5fa; /* blue-400: 暗い popover 上で読みやすい青 */
  }
  .changelog-md :global(code) {
    border-radius: 0.25rem;
    background: var(--muted);
    padding: 0.1rem 0.3rem;
    font-size: 0.85em;
  }
  .changelog-md :global(pre) {
    overflow-x: auto;
    border-radius: 0.5rem;
    background: var(--muted);
    padding: 0.75rem;
  }
  .changelog-md :global(pre code) {
    background: transparent;
    padding: 0;
  }
  .changelog-md :global(hr) {
    margin: 1rem 0;
    border-color: var(--border);
  }
</style>
