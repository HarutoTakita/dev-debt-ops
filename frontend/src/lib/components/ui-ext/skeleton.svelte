<script lang="ts">
  import { cn } from "$lib/utils";

  // レイアウト準拠スケルトンの最小部品（ui/ 外。ui/ 直下は読み取り専用のため）。
  // 利用側は最終レイアウトと同じ形・サイズのクラスを渡して CLS を防ぐ。
  let { class: className }: { class?: string } = $props();
</script>

<div class={cn("animate-pulse rounded-md bg-muted", className)} aria-hidden="true"></div>
