<script lang="ts">
  type Props = {
    path: string | null;
    content: string | null;
    size: number;
    loading: boolean;
  };

  const { path, content, size, loading }: Props = $props();

  function formatBytes(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  function langFromPath(p: string): string {
    const ext = p.split(".").at(-1) ?? "";
    const map: Record<string, string> = {
      ts: "typescript",
      tsx: "typescript",
      js: "javascript",
      jsx: "javascript",
      svelte: "svelte",
      py: "python",
      rs: "rust",
      go: "go",
      java: "java",
      rb: "ruby",
      php: "php",
      css: "css",
      html: "html",
      json: "json",
      yaml: "yaml",
      yml: "yaml",
      toml: "toml",
      md: "markdown",
      sh: "bash",
      sql: "sql",
    };
    return map[ext] ?? "plaintext";
  }
</script>

<div class="flex h-full flex-col">
  {#if !path}
    <div class="flex h-full items-center justify-center text-sm text-muted-foreground">ファイルを選択してください</div>
  {:else if loading}
    <div class="flex h-full items-center justify-center text-sm text-muted-foreground">読み込み中...</div>
  {:else}
    <div class="flex items-center justify-between border-b px-4 py-2 font-mono text-xs text-muted-foreground">
      <span>{path}</span>
      <span>{formatBytes(size)}</span>
    </div>
    <div class="flex-1 overflow-auto">
      {#if content !== null}
        <pre class="p-4 font-mono text-xs leading-relaxed"><code class="language-{langFromPath(path)}">{content}</code
          ></pre>
      {:else}
        <div class="flex h-full items-center justify-center text-sm text-muted-foreground">
          バイナリファイル ({formatBytes(size)})
        </div>
      {/if}
    </div>
  {/if}
</div>
