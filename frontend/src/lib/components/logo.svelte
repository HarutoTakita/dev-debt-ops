<script lang="ts">
  import { cn } from "$lib/utils";

  interface Props {
    class?: string;
  }

  let { class: className }: Props = $props();
</script>

<!-- DevDebtOps のレターマーク（R）。currentColor で着色し利用側のテキスト色を継承する。
     static/favicon.svg の「R」マークとブランド整合。 -->
<svg
  xmlns="http://www.w3.org/2000/svg"
  viewBox="0 0 32 32"
  fill="currentColor"
  class={cn("size-6", className)}
  aria-hidden="true"
>
  <text
    x="16"
    y="25"
    font-family="Georgia, 'Times New Roman', serif"
    font-size="26"
    font-weight="bold"
    text-anchor="middle"
    fill="currentColor">D</text
  >
</svg>
