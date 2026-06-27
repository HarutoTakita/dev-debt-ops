<script lang="ts">
  import { page } from "$app/state";
  import { resolve } from "$app/paths";
  import { cn } from "$lib/utils";
  import { Badge } from "$lib/components/ui/badge";
  import * as Tooltip from "$lib/components/ui/tooltip";
  import { sidebar } from "$lib/stores/sidebar-store.svelte";
  import { isActiveRoute, type NavContext, type NavItem } from "$lib/config/nav";
  import * as m from "$lib/paraglide/messages";

  // showPill: ダミー/グローバルな pill 値（KC% など）はアクティブプロジェクトでのみ意味を持つため、
  // 非アクティブなプロジェクトのメニューでは pill を抑止する（全プロジェクトに同値を出さない）。
  let { item, ctx, showPill = true }: { item: NavItem; ctx: NavContext; showPill?: boolean } = $props();

  const route = $derived(item.route(ctx));
  const enabled = $derived(item.enabled ? item.enabled(ctx) : true);
  const active = $derived(isActiveRoute(route, page.url.pathname, item.exact));
  const pillText = $derived(showPill ? (item.pill?.(ctx) ?? null) : null);
  const Icon = $derived(item.icon);

  const baseRow = "flex h-9 items-center gap-2.5 rounded-md px-2.5 text-sm transition-colors";
  const activeCls = "bg-accent text-foreground font-medium";
  const inactiveCls = "text-muted-foreground hover:bg-accent/50 hover:text-foreground";
</script>

{#if !enabled}
  <!-- 無効項目もキーボードで発見できるよう、フォーカス可能な aria-disabled リンク + Soon バッジにする（rank33）。 -->
  <span
    role="link"
    aria-disabled="true"
    tabindex="0"
    class={cn(
      baseRow,
      "cursor-not-allowed text-muted-foreground/60 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
      sidebar.collapsed && "justify-center",
    )}
    title={item.label()}
  >
    <Icon class="size-4 shrink-0" />
    {#if !sidebar.collapsed}
      <span class="flex-1 truncate">{item.label()}</span>
      <Badge variant="outline" class="h-5 px-1.5 text-[10px] text-muted-foreground">{m.shell_soon()}</Badge>
    {/if}
  </span>
{:else if sidebar.collapsed}
  <Tooltip.Root>
    <Tooltip.Trigger>
      {#snippet child({ props })}
        <a
          {...props}
          href={resolve(route)}
          aria-current={active ? "page" : undefined}
          data-tour={`nav-${item.id}`}
          class={cn(baseRow, "justify-center", active ? activeCls : inactiveCls)}
        >
          <Icon class="size-4" />
        </a>
      {/snippet}
    </Tooltip.Trigger>
    <Tooltip.Content side="right" class="flex items-center gap-2">
      <span>{item.label()}</span>
      {#if pillText}
        <span class="opacity-70">{pillText}</span>
      {/if}
    </Tooltip.Content>
  </Tooltip.Root>
{:else}
  <a
    href={resolve(route)}
    aria-current={active ? "page" : undefined}
    data-tour={`nav-${item.id}`}
    class={cn(baseRow, active ? activeCls : inactiveCls)}
  >
    <Icon class="size-4 shrink-0" />
    <span class="flex-1 truncate">{item.label()}</span>
    {#if pillText}
      <Badge variant={active ? "secondary" : "outline"} class="h-5 px-1.5 text-[10px] font-medium tabular-nums">
        {pillText}
      </Badge>
    {/if}
  </a>
{/if}
