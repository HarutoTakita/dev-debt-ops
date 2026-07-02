<script lang="ts">
  import { cn } from "$lib/utils";

  interface Props {
    class?: string;
  }

  let { class: className }: Props = $props();
</script>

<!-- アプリアイコン（static/favicon.svg）と完全一致のブランドマーク。DevDebtOps デュアルループ:
     ティール上弧（理解度・実測）＋アンバー下弧（コード・返済）が矢じり付きで回り「測って返す」閉ループを
     象徴する。角丸ダーク地の**バッジ込み**でアプリアイコンと同一の見た目にする（2 色固定・currentColor 不使用）。 -->
<svg
  xmlns="http://www.w3.org/2000/svg"
  viewBox="0 0 32 32"
  fill="none"
  class={cn("size-6", className)}
  aria-hidden="true"
>
  <rect width="32" height="32" rx="8" fill="#0c1116" />
  <path d="M8.21 11.5 A9 9 0 0 1 23.79 11.5" fill="none" stroke="#22b8c4" stroke-width="3.2" stroke-linecap="round" />
  <path d="M25.09 13.75 L22.14 12.45 L25.44 10.55 Z" fill="#22b8c4" />
  <path d="M23.79 20.5 A9 9 0 0 1 8.21 20.5" fill="none" stroke="#e0a23a" stroke-width="3.2" stroke-linecap="round" />
  <path d="M6.91 18.25 L9.86 19.55 L6.56 21.45 Z" fill="#e0a23a" />
</svg>
