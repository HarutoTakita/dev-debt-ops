<script lang="ts">
  import { resolve } from "$app/paths";
  import type { ResolvedPathname } from "$app/types";
  import type { FileDebt } from "$lib/api/schemas";
  import { cn } from "$lib/utils";
  import * as m from "$lib/paraglide/messages";

  // 推移グラフの隣に並べる「品質 × 理解」4 象限の件数内訳。マトリクスと同じ 2 軸（KC×コード品質）で
  // ファイルを 4 象限に分類し、件数 + 割合バーで分布を示す。各行は /matrix?cell= の入口（凡例と整合）。
  type Props = { orgSlug: string; projectSlug: string; files: FileDebt[] };
  const { orgSlug, projectSlug, files }: Props = $props();

  const matrixHref = $derived(resolve(`/${orgSlug}/${projectSlug}/matrix`));

  // 閾値 0.5 はマトリクス / dangerCount と一致。high quality = code_debt_score <= 0.5。
  const buckets = $derived.by(() => {
    const c = { danger: 0, code_repay: 0, refactor: 0, ideal: 0 };
    for (const f of files) {
      const lowKc = f.knowledge_coverage < 0.5;
      const dirty = f.code_debt_score > 0.5;
      if (lowKc && dirty) c.danger++;
      else if (lowKc && !dirty) c.code_repay++;
      else if (!lowKc && dirty) c.refactor++;
      else c.ideal++;
    }
    return c;
  });
  const total = $derived(files.length || 1);

  const rows = $derived<{ key: string; label: string; count: number; dot: string; href: ResolvedPathname }[]>([
    {
      key: "danger",
      label: m.overview_quadrant_danger(),
      count: buckets.danger,
      dot: "bg-destructive",
      href: `${matrixHref}?cell=danger` as ResolvedPathname,
    },
    {
      key: "code_repay",
      label: m.overview_quadrant_code_repay(),
      count: buckets.code_repay,
      dot: "bg-debt-knowledge",
      href: `${matrixHref}?cell=code_repay` as ResolvedPathname,
    },
    {
      key: "refactor",
      label: m.overview_quadrant_refactor(),
      count: buckets.refactor,
      dot: "bg-debt-code",
      href: `${matrixHref}?cell=refactor` as ResolvedPathname,
    },
    {
      key: "ideal",
      label: m.overview_quadrant_ideal(),
      count: buckets.ideal,
      dot: "bg-success",
      href: `${matrixHref}?cell=ideal` as ResolvedPathname,
    },
  ]);
</script>

<div class="flex flex-col rounded-lg border bg-card p-4">
  <div class="text-sm font-medium">{m.overview_breakdown_title()}</div>
  <ul class="mt-3 flex flex-1 flex-col justify-between gap-3">
    {#each rows as r (r.key)}
      <li>
        <a href={r.href} class="group flex items-center gap-2 text-sm">
          <span class={cn("size-2 shrink-0 rounded-full", r.dot)}></span>
          <span class="min-w-0 flex-1 truncate text-muted-foreground group-hover:text-foreground">{r.label}</span>
          <span class="shrink-0 tabular-nums">{m.overview_scatter_count({ count: r.count })}</span>
        </a>
        <!-- 件数割合のバー（象限色） -->
        <div class="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-muted">
          <div class={cn("h-full rounded-full", r.dot)} style="width: {(r.count / total) * 100}%"></div>
        </div>
      </li>
    {/each}
  </ul>
</div>
