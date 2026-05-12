<script lang="ts">
  import { cn } from "$lib/utils";

  interface Props {
    class?: string;
  }

  let { class: className }: Props = $props();
</script>

<svg
  xmlns="http://www.w3.org/2000/svg"
  viewBox="-10 -10 110.6 71.5"
  fill="currentColor"
  class={cn("size-6", className)}
  aria-hidden="true"
>
  <path
    d="M56.6.1l16.9 29.3L90.4.1zm3.7 20.6L48.4.1h-9.2l11.9 20.6 13.7 23.7 4.6-8zm-11 10.6h-9.4l1.7 3-6 10.5-10.4-17.9h21.5L31.3.1H.3l8.3 14.3H18l-3.6-6.2h12.2l6.1 10.6-21.5.1 4.6 8 19.8 34.2L51 34.3z"
    stroke="currentColor"
    stroke-width="0.5"
  />
</svg>
