<script lang="ts">
  import Pin from "@lucide/svelte/icons/pin";
  import PinOff from "@lucide/svelte/icons/pin-off";
  import { page } from "$app/state";
  import { resolve } from "$app/paths";
  import { cn } from "$lib/utils";
  import { Badge } from "$lib/components/ui/badge";
  import * as Tooltip from "$lib/components/ui/tooltip";
  import { sidebar } from "$lib/stores/sidebar-store.svelte";
  import { isActiveRoute, type NavContext, type NavItem } from "$lib/config/nav";
  import * as m from "$lib/paraglide/messages";

  let { item, ctx }: { item: NavItem; ctx: NavContext } = $props();

  const route = $derived(item.route(ctx));
  const enabled = $derived(item.enabled ? item.enabled(ctx) : true);
  const active = $derived(isActiveRoute(route, page.url.pathname, item.exact));
  const pillText = $derived(item.pill?.(ctx) ?? null);
  const pinned = $derived(sidebar.isPinned(item.id));
  const Icon = $derived(item.icon);

  const baseRow = "flex h-9 items-center gap-2.5 rounded-md px-2.5 text-sm transition-colors";
  const activeCls = "bg-accent text-foreground font-medium";
  const inactiveCls = "text-muted-foreground hover:bg-accent/50 hover:text-foreground";
</script>

{#if !enabled}
  <div
    class={cn(baseRow, "cursor-not-allowed text-muted-foreground/40", sidebar.collapsed && "justify-center")}
    title={item.label()}
  >
    <Icon class="size-4 shrink-0" />
    {#if !sidebar.collapsed}<span class="flex-1 truncate">{item.label()}</span>{/if}
  </div>
{:else if sidebar.collapsed}
  <Tooltip.Root>
    <Tooltip.Trigger>
      {#snippet child({ props })}
        <a
          {...props}
          href={resolve(route)}
          aria-current={active ? "page" : undefined}
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
      {:else if item.comingSoon}
        <span class="opacity-70">{m.shell_soon()}</span>
      {/if}
    </Tooltip.Content>
  </Tooltip.Root>
{:else}
  <div class="group/navitem relative">
    <a
      href={resolve(route)}
      aria-current={active ? "page" : undefined}
      class={cn(baseRow, active ? activeCls : inactiveCls, item.comingSoon && "opacity-90")}
    >
      <Icon class="size-4 shrink-0" />
      <span class="flex-1 truncate">{item.label()}</span>
      {#if pillText}
        <Badge variant={active ? "secondary" : "outline"} class="h-5 px-1.5 text-[10px] font-medium tabular-nums">
          {pillText}
        </Badge>
      {:else if item.comingSoon}
        <Badge variant="outline" class="h-5 px-1.5 text-[10px] text-muted-foreground">{m.shell_soon()}</Badge>
      {/if}
    </a>
    {#if item.pinnable !== false}
      <button
        type="button"
        onclick={() => sidebar.togglePin(item.id)}
        aria-label={pinned ? m.shell_unpin() : m.shell_pin()}
        title={pinned ? m.shell_unpin() : m.shell_pin()}
        class={cn(
          "absolute top-1/2 right-1.5 -translate-y-1/2 rounded p-1 hover:bg-background hover:text-foreground",
          pinned ? "text-foreground opacity-100" : "text-muted-foreground opacity-0 group-hover/navitem:opacity-100",
        )}
      >
        {#if pinned}<PinOff class="size-3" />{:else}<Pin class="size-3" />{/if}
      </button>
    {/if}
  </div>
{/if}
