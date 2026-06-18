<script lang="ts">
  import hljs from "highlight.js";
  import type { Snippet } from "svelte";

  type Props = {
    path: string | null;
    content: string | null;
    size: number;
    loading: boolean;
    /**
     * 知識オーバーレイ層。ソース層の上に重ねる KC ヒートマップ行 / 考古学注釈を後続 issue が描く。
     * 本 issue では未使用（二層構造の土台のみ用意）。
     */
    overlayRow?: Snippet;
  };

  const { path, content, size, loading, overlayRow }: Props = $props();

  // GitLab の blob_viewers/index.js (loadViewer) に倣ったビューア種別ディスパッチ。
  type ViewerKind = "text" | "image" | "binary" | "too_large" | "empty";
  const IMAGE_EXT = new Set(["png", "jpg", "jpeg", "gif", "webp", "svg", "avif"]);
  const TOO_LARGE_BYTES = 1024 * 1024; // 1 MB

  // 拡張子 → highlight.js 言語。svelte/html は xml で代替（hljs に svelte 言語はない）。
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

  function extOf(p: string): string {
    return p.split(".").at(-1)?.toLowerCase() ?? "";
  }

  function formatBytes(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  function resolveViewer(p: string, sz: number, c: string | null): ViewerKind {
    if (sz === 0) return "empty";
    if (sz > TOO_LARGE_BYTES) return "too_large";
    const ext = extOf(p);
    if (IMAGE_EXT.has(ext)) return "image";
    if (c === null) return "binary"; // API がデコード不能で content=null を返した
    return "text";
  }

  const kind = $derived(path ? resolveViewer(path, size, content) : null);

  // ソース層: highlight.js で構文ハイライト。失敗時は素のテキストへフォールバック。
  const rendered = $derived.by<{ html: string } | { text: string }>(() => {
    if (kind !== "text" || content === null || path === null) return { text: "" };
    const lang = LANG_MAP[extOf(path)];
    try {
      const value =
        lang && hljs.getLanguage(lang)
          ? hljs.highlight(content, { language: lang }).value
          : hljs.highlightAuto(content).value;
      return { html: value };
    } catch {
      return { text: content };
    }
  });
</script>

<div class="flex h-full flex-col">
  {#if !path}
    <div class="flex h-full items-center justify-center text-sm text-muted-foreground">ファイルを選択してください</div>
  {:else if loading}
    <div class="flex h-full items-center justify-center text-sm text-muted-foreground">読み込み中...</div>
  {:else if kind === "empty"}
    <div class="flex h-full items-center justify-center text-sm text-muted-foreground">空のファイルです</div>
  {:else if kind === "too_large"}
    <div class="flex h-full flex-col items-center justify-center gap-1 text-sm text-muted-foreground">
      <span>ファイルが大きすぎます</span>
      <span class="text-xs">{formatBytes(size)} — プレビュー不可</span>
    </div>
  {:else if kind === "image"}
    <div class="flex h-full flex-col items-center justify-center gap-1 text-sm text-muted-foreground">
      <span>画像ファイル</span>
      <span class="text-xs">{formatBytes(size)} — プレビューは未対応</span>
    </div>
  {:else if kind === "binary"}
    <div class="flex h-full flex-col items-center justify-center gap-1 text-sm text-muted-foreground">
      <span>バイナリファイル</span>
      <span class="text-xs">{formatBytes(size)} — プレビュー不可</span>
    </div>
  {:else}
    <!-- text: 二層構造（下層 = ハイライト済みソース / 上層 = 知識オーバーレイ枠） -->
    <div class="relative h-full overflow-auto">
      {#if overlayRow}
        <div class="pointer-events-none absolute inset-0 z-10">{@render overlayRow()}</div>
      {/if}
      <!-- eslint-disable svelte/no-at-html-tags -- hljs はソースを HTML エスケープしてから着色するため、HTML 注入は起きない -->
      <pre class="hljs !bg-transparent px-4 py-3 font-mono text-xs leading-relaxed"><code
          >{#if "html" in rendered}{@html rendered.html}{:else}{rendered.text}{/if}</code
        ></pre>
      <!-- eslint-enable svelte/no-at-html-tags -->
    </div>
  {/if}
</div>
