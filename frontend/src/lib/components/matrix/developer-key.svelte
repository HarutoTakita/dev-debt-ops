<script lang="ts">
  import * as m from "$lib/paraglide/messages";

  // アバターの緑/破線エンコーディングの意味を、ツールチップだけでなくインラインで明示する。
  // developer-avatar.svelte の border-success（理解者）/ border-dashed（レビューのみ）と 1:1 で対応。
</script>

<span class="inline-flex items-center gap-2 text-[10px] whitespace-nowrap text-muted-foreground">
  <span class="inline-flex items-center gap-1">
    <span class="size-2.5 rounded-full border-2 border-success bg-success/20"></span>
    {m.matrix_avatar_understood()}
  </span>
  <span class="inline-flex items-center gap-1">
    <span class="size-2.5 rounded-full border-2 border-dashed border-muted-foreground/40"></span>
    {m.matrix_avatar_review()}
  </span>
</span>
