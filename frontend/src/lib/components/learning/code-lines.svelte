<script lang="ts">
  import hljs from "highlight.js";
  import { cn } from "$lib/utils";

  // 行番号つきソース表示 + 指定行範囲のハイライト。コード理解ウォークスルー（code-walkthrough）/
  // コード改善 / コード品質マップのファイルビューで共用する。範囲が変わると先頭行を中央へスクロールする。
  // containerClass で高さ/枠を呼び出し側に合わせる（既定はウォークスルー用の固定高）。
  type Props = {
    content: string;
    path: string;
    highlightStart: number;
    highlightEnd: number;
    containerClass?: string;
  };
  const {
    content,
    path,
    highlightStart,
    highlightEnd,
    containerClass = "max-h-[72vh] overflow-auto rounded-lg border bg-card font-mono text-xs",
  }: Props = $props();

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

  function isActive(lineNo: number): boolean {
    return highlightStart > 0 && lineNo >= highlightStart && lineNo <= highlightEnd;
  }

  let codeEl = $state<HTMLDivElement | null>(null);
  // ハイライト範囲が変わるたびに先頭行を中央へスクロール。
  $effect(() => {
    void highlightStart;
    if (!codeEl || highlightStart <= 0) return;
    const target = codeEl.querySelector(`[data-line="${highlightStart}"]`);
    target?.scrollIntoView({ block: "center", behavior: "smooth" });
  });
</script>

<div bind:this={codeEl} class={containerClass}>
  <!-- 内側ラッパを w-max（最長行の幅・最低でもコンテナ幅）にし、各行は自動幅でラッパ幅いっぱいに伸ばす。
       これでハイライト背景が短い行でも最長行までの全幅に広がり、横スクロールしても途切れない（issue 231）。 -->
  <div class="w-max min-w-full">
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
</div>
