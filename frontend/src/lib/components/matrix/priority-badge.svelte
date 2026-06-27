<script lang="ts">
  import { cn } from "$lib/utils";
  import * as m from "$lib/paraglide/messages";
  import { derivePriority, priorityLabel, type Priority } from "./priority";

  // 二軸座標から導いた優先度を、ピル内の 2 本ミニゲージ（左=コード負債軸 / 右=ナレッジ負債軸）で示す。
  type Props = { code: number; coverage: number };
  const { code, coverage }: Props = $props();

  const know = $derived(1 - coverage); // 理解の欠落度
  const priority = $derived(derivePriority(code, know));
  const label = $derived(priorityLabel(priority));

  const tone: Record<Priority, string> = {
    P0: "bg-destructive/15 text-destructive ring-1 ring-destructive/30",
    P1: "bg-warning/15 text-warning",
    P2: "bg-muted text-foreground/70",
    P3: "bg-muted/60 text-muted-foreground",
  };
</script>

<div
  class={cn("inline-flex items-center gap-1.5 rounded px-1.5 py-1 text-xs font-semibold tabular-nums", tone[priority])}
  title={m.matrix_priority_title({ code: Math.round(code * 100), know: Math.round(know * 100) })}
>
  <span>{label}</span>
  <!-- 2 本ミニゲージ。P0 ほど両方が満ちる（最危険ゾーン）。色は currentColor を継承。
       色のみ符号化を避けるため、優先度 + 2 軸値を SR 向けに読み上げる（rank10）。 -->
  <span
    class="flex h-3 items-end gap-0.5"
    role="img"
    aria-label={m.matrix_priority_aria({
      priority: label,
      code: Math.round(code * 100),
      know: Math.round(know * 100),
    })}
  >
    <span class="relative inline-block h-3 w-1 rounded-xs bg-current/20">
      <span class="absolute bottom-0 left-0 w-full rounded-xs bg-current" style="height: {Math.round(code * 100)}%"
      ></span>
    </span>
    <span class="relative inline-block h-3 w-1 rounded-xs bg-current/20">
      <span class="absolute bottom-0 left-0 w-full rounded-xs bg-current" style="height: {Math.round(know * 100)}%"
      ></span>
    </span>
  </span>
</div>
