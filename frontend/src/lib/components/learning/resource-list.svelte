<script lang="ts">
  import type { LearningStep } from "$lib/api/schemas";
  import ResourceCard from "./resource-card.svelte";
  import * as m from "$lib/paraglide/messages";

  // 2 セクション（issue 068）: code=このコードを理解する（具体）/ stack=技術スタックを学ぶ（一般）。
  type Props = { steps: LearningStep[]; ontoggle?: (order: number, completed: boolean) => void };
  const { steps, ontoggle }: Props = $props();

  // 空のウォークスルー（walkthrough_steps === 0）の code 解説カードだけ出さない（開いても「解説はまだ
  // ありません」で見栄えが悪いため）。ただし手順数が未定義（旧 API 等でフィールド欠落）のときは「不明」として
  // 表示する＝fail-open。`> 0` だと欠落時に code セクションが丸ごと消えてしまうため、`?? 1` で既定表示にする。
  // stack（外部リンク）は対象外。
  const codeSteps = $derived(
    steps
      .filter((s) => s.resource.section === "code" && (s.resource.walkthrough_steps ?? 1) > 0)
      .sort((a, b) => a.order - b.order),
  );
  const stackSteps = $derived(steps.filter((s) => s.resource.section === "stack").sort((a, b) => a.order - b.order));
</script>

<div class="grid gap-5 lg:grid-cols-2 lg:items-start">
  {#if codeSteps.length > 0}
    <section class="min-w-0" data-tour="plan-code">
      <h3 class="font-display text-sm font-semibold text-debt-knowledge">{m.learning_code_heading()}</h3>
      <div class="mt-2 space-y-2">
        {#each codeSteps as s, i (s.order)}
          <!-- 先頭の 1 件はガイドのハイライト対象（このコードを理解する）。 -->
          <div data-tour={i === 0 ? "plan-code-first" : undefined}>
            <ResourceCard resource={s.resource} completed={s.completed} order={s.order} {ontoggle} />
          </div>
        {/each}
      </div>
    </section>
  {/if}

  {#if stackSteps.length > 0}
    <section class="min-w-0" data-tour="plan-stack">
      <h3 class="font-display text-sm font-semibold text-debt-knowledge">{m.learning_stack_heading()}</h3>
      <div class="mt-2 space-y-2">
        {#each stackSteps as s, i (s.order)}
          <!-- 先頭の 1 件はガイドのハイライト対象（技術スタックを学ぶ）。 -->
          <div data-tour={i === 0 ? "plan-stack-first" : undefined}>
            <ResourceCard resource={s.resource} completed={s.completed} order={s.order} {ontoggle} />
          </div>
        {/each}
      </div>
    </section>
  {/if}
</div>
