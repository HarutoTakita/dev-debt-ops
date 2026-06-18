<script lang="ts">
  import type { QuizQuestion } from "$lib/api/schemas";
  import FileViewer from "$lib/components/repo/file-viewer.svelte";

  // クイズ設問のコードスニペット表示。既存 file-viewer の構文ハイライトを再利用する。
  type Props = { snippet: NonNullable<QuizQuestion["code_snippet"]> };
  const { snippet }: Props = $props();
</script>

<div class="flex h-full flex-col overflow-hidden rounded-lg border bg-card">
  <div class="shrink-0 border-b px-3 py-1.5 font-mono text-xs text-muted-foreground">{snippet.path}</div>
  <div class="min-h-0 flex-1 overflow-auto">
    <FileViewer path={snippet.path} content={snippet.content} size={snippet.content.length} loading={false} />
  </div>
</div>
