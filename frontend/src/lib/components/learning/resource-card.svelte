<script lang="ts">
  import FileText from "@lucide/svelte/icons/file-text";
  import Video from "@lucide/svelte/icons/video";
  import MessageSquare from "@lucide/svelte/icons/message-square";
  import BookOpen from "@lucide/svelte/icons/book-open";
  import Book from "@lucide/svelte/icons/book";
  import Code from "@lucide/svelte/icons/code";
  import Newspaper from "@lucide/svelte/icons/newspaper";
  import Check from "@lucide/svelte/icons/check";
  import ExternalLink from "@lucide/svelte/icons/external-link";
  import { page } from "$app/state";
  import { resolve } from "$app/paths";
  import type { ResolvedPathname } from "$app/types";
  import type { LearningResource, ResourceKind, ResourcePriority } from "$lib/api/schemas";
  import { cn } from "$lib/utils";
  import * as m from "$lib/paraglide/messages";

  // リソース 1 件カード（種別アイコン・出典・所要時間・必須/推奨/補助・死蔵バッジ）。
  // ontoggle が渡されれば完了トグル（PATCH、issue 035）を有効化する。
  type Props = {
    resource: LearningResource;
    completed: boolean;
    order?: number;
    ontoggle?: (order: number, completed: boolean) => void;
  };
  const { resource, completed, order, ontoggle }: Props = $props();

  const ICON: Record<ResourceKind, typeof FileText> = {
    adr: FileText,
    video: Video,
    pr_comment: MessageSquare,
    wiki: BookOpen,
    docs: FileText,
    book: Book,
    article: Newspaper,
    code: Code,
  };
  const Icon = $derived(ICON[resource.kind]);

  const priorityLabel: Record<ResourcePriority, string> = {
    required: m.learning_priority_required(),
    recommended: m.learning_priority_recommended(),
    supplementary: m.learning_priority_supplementary(),
    hands_on: m.learning_priority_hands_on(),
  };
  const priorityTone: Record<ResourcePriority, string> = {
    required: "bg-debt-code/15 text-debt-code",
    recommended: "bg-muted text-foreground/70",
    supplementary: "bg-muted/60 text-muted-foreground",
    hands_on: "bg-debt-knowledge/15 text-debt-knowledge",
  };

  const dormantMonths = $derived(resource.dormant_days != null ? Math.round(resource.dormant_days / 30) : null);

  // 教材を開くリンク: 外部資源は URL（別タブ）、チーム資産はリポジトリビューアの該当ファイルへ。
  const orgSlug = $derived(page.params.org ?? "");
  const projectSlug = $derived(page.params.project ?? "");
  const isExternal = $derived(Boolean(resource.url));
  const href = $derived.by((): string | null => {
    if (resource.url) return resource.url;
    if (resource.source_ref)
      return `${resolve(`/${orgSlug}/${projectSlug}/repos`)}?path=${encodeURIComponent(resource.source_ref)}` as ResolvedPathname;
    return null;
  });
</script>

<div class="flex items-start gap-3 rounded-lg border bg-card p-3">
  <Icon class="mt-0.5 size-4 shrink-0 text-muted-foreground" />
  <div class="min-w-0 flex-1">
    <div class="flex items-center gap-2">
      {#if href}
        <!-- href は外部資源 URL もしくは resolve() 済みのリポジトリパス（混在のため動的） -->
        <!-- eslint-disable svelte/no-navigation-without-resolve -->
        <a
          {href}
          target={isExternal ? "_blank" : undefined}
          rel={isExternal ? "noopener noreferrer" : undefined}
          class="inline-flex min-w-0 items-center gap-1 text-sm font-medium text-primary hover:underline"
        >
          <span class="truncate">{resource.title}</span>
          {#if isExternal}<ExternalLink class="size-3 shrink-0" />{/if}
        </a>
        <!-- eslint-enable svelte/no-navigation-without-resolve -->
      {:else}
        <span class="truncate text-sm font-medium">{resource.title}</span>
      {/if}
      {#if ontoggle && order != null}
        <button
          type="button"
          onclick={() => ontoggle(order, !completed)}
          aria-pressed={completed}
          aria-label={m.learning_toggle_done()}
          class="shrink-0 rounded-full border p-0.5 {completed
            ? 'border-success text-success'
            : 'border-muted-foreground/40 text-transparent hover:text-muted-foreground/40'}"
        >
          <Check class="size-3" />
        </button>
      {:else if completed}
        <Check class="size-3.5 shrink-0 text-success" />
      {/if}
    </div>
    {#if resource.source_ref}<p class="truncate text-xs text-muted-foreground">{resource.source_ref}</p>{/if}
    {#if resource.summary}
      <p class="mt-1 text-xs leading-relaxed text-muted-foreground">{resource.summary}</p>
    {/if}
    {#if dormantMonths != null}
      <p class="mt-1 text-xs text-debt-code">🕸 {m.learning_dormant({ months: dormantMonths })}</p>
    {/if}
  </div>
  <div class="flex shrink-0 flex-col items-end gap-1">
    <span class={cn("rounded px-1.5 py-0.5 text-[10px] font-medium", priorityTone[resource.priority])}>
      {priorityLabel[resource.priority]}
    </span>
    {#if resource.estimated_minutes != null}
      <span class="text-xs text-muted-foreground tabular-nums">{resource.estimated_minutes}分</span>
    {/if}
  </div>
</div>
