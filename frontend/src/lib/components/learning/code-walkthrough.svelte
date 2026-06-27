<script lang="ts">
  import hljs from "highlight.js";
  import ChevronLeft from "@lucide/svelte/icons/chevron-left";
  import ChevronRight from "@lucide/svelte/icons/chevron-right";
  import type { CodeWalkthroughStep } from "$lib/api/schemas";
  import { cn } from "$lib/utils";
  import * as m from "$lib/paraglide/messages";

  // コード理解ウォークスルー: ソースを行ごとに表示し、step ごとに該当行をハイライト＋スクロールしながら解説する。
  type Props = { content: string; path: string; steps: CodeWalkthroughStep[] };
  const { content, path, steps }: Props = $props();

  // 拡張子 → highlight.js 言語（file-viewer.svelte と同方針。svelte/html は xml で代替）。
  const LANG_MAP: Record<string, string> = {
    ts: "typescript",
    tsx: "typescript",
    js: "javascript",
    jsx: "javascript",
    svelte: "xml",
    py: "python",
    rs: "rust",
    go: "go",
    java: "java",
    rb: "ruby",
    php: "php",
    css: "css",
    html: "xml",
    json: "json",
    yaml: "yaml",
    yml: "yaml",
    toml: "ini",
    md: "markdown",
    sh: "bash",
    sql: "sql",
  };
  const lang = $derived(LANG_MAP[path.split(".").at(-1)?.toLowerCase() ?? ""]);

  function escapeHtml(s: string): string {
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
  // 行ごとに着色（複数行トークンは簡易許容）。言語不明な行は素のテキストをエスケープのみ。
  const lines = $derived.by(() =>
    content.split("\n").map((line) => {
      if (lang && hljs.getLanguage(lang)) {
        try {
          return hljs.highlight(line, { language: lang }).value;
        } catch {
          return escapeHtml(line);
        }
      }
      return escapeHtml(line);
    }),
  );

  let idx = $state(0);
  const active = $derived(steps[idx]);
  const total = $derived(steps.length);

  function isActive(lineNo: number): boolean {
    return active != null && lineNo >= active.start_line && lineNo <= active.end_line;
  }

  function go(next: number) {
    idx = Math.max(0, Math.min(total - 1, next));
  }

  function onKey(e: KeyboardEvent) {
    if (e.key === "ArrowRight") go(idx + 1);
    else if (e.key === "ArrowLeft") go(idx - 1);
  }

  let codeEl = $state<HTMLDivElement | null>(null);
  // step が変わるたびに該当範囲の先頭行を中央へスクロール。
  $effect(() => {
    void idx;
    if (!codeEl || active == null) return;
    const target = codeEl.querySelector(`[data-line="${active.start_line}"]`);
    target?.scrollIntoView({ block: "center", behavior: "smooth" });
  });
</script>

<svelte:window onkeydown={onKey} />

<div class="grid gap-4 lg:grid-cols-[1.7fr_1fr] lg:items-start">
  <!-- 左: 行ごとのソース表示 -->
  <div bind:this={codeEl} class="max-h-[72vh] overflow-auto rounded-lg border bg-card font-mono text-xs">
    {#each lines as html, i (i)}
      {@const lineNo = i + 1}
      <div
        data-line={lineNo}
        class={cn(
          "flex border-l-2 border-transparent",
          isActive(lineNo) && "border-debt-knowledge bg-debt-knowledge/10",
        )}
      >
        <span class="w-12 shrink-0 px-2 py-0.5 text-right text-muted-foreground/60 tabular-nums select-none">
          {lineNo}
        </span>
        <!-- eslint-disable svelte/no-at-html-tags -- hljs はソースを HTML エスケープしてから着色するため安全 -->
        <pre class="hljs overflow-visible !bg-transparent px-2 py-0.5 leading-relaxed"><code>{@html html || " "}</code
          ></pre>
        <!-- eslint-enable svelte/no-at-html-tags -->
      </div>
    {/each}
  </div>

  <!-- 右: 現在 step の解説 + ナビ。固定高 + 解説をスクロール領域にして移動ボタンを毎ステップ同じ位置に固定。 -->
  <div class="lg:sticky lg:top-4">
    <div class="flex min-h-[18rem] flex-col rounded-lg border bg-card p-4 lg:h-[72vh]">
      <div class="flex shrink-0 items-center justify-between gap-2">
        <span class="text-xs font-medium text-muted-foreground tabular-nums">
          {m.walkthrough_step({ current: total === 0 ? 0 : idx + 1, total })}
        </span>
        {#if active}
          <span class="text-xs text-muted-foreground tabular-nums">
            L{active.start_line}{active.end_line !== active.start_line ? `–${active.end_line}` : ""}
          </span>
        {/if}
      </div>
      <div class="mt-2 flex-1 overflow-auto">
        {#if active}
          {#if active.title}
            <h3 class="font-display text-sm font-semibold text-debt-knowledge">{active.title}</h3>
          {/if}
          <p class="mt-1.5 text-sm leading-relaxed">{active.explanation}</p>
        {:else}
          <p class="text-sm text-muted-foreground">{m.walkthrough_empty()}</p>
        {/if}
      </div>
      <div class="mt-3 flex shrink-0 items-center justify-between gap-2 border-t pt-3">
        <button
          type="button"
          onclick={() => go(idx - 1)}
          disabled={idx <= 0}
          class="inline-flex items-center gap-1 rounded-md border px-2.5 py-1 text-xs font-medium hover:bg-accent/40 disabled:opacity-40"
        >
          <ChevronLeft class="size-3.5" />
          {m.walkthrough_prev()}
        </button>
        <button
          type="button"
          onclick={() => go(idx + 1)}
          disabled={idx >= total - 1}
          class="inline-flex items-center gap-1 rounded-md border px-2.5 py-1 text-xs font-medium text-debt-knowledge hover:bg-accent/40 disabled:opacity-40"
        >
          {m.walkthrough_next()}
          <ChevronRight class="size-3.5" />
        </button>
      </div>
    </div>
  </div>
</div>
