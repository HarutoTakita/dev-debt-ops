<script lang="ts">
  import ChevronDown from "@lucide/svelte/icons/chevron-down";
  import FolderGit2 from "@lucide/svelte/icons/folder-git-2";
  import Star from "@lucide/svelte/icons/star";
  import MoreHorizontal from "@lucide/svelte/icons/more-horizontal";
  import Check from "@lucide/svelte/icons/check";
  import Plus from "@lucide/svelte/icons/plus";
  import { cn } from "$lib/utils";
  import * as Collapsible from "$lib/components/ui/collapsible";
  import * as DropdownMenu from "$lib/components/ui/dropdown-menu";
  import { allNavItems, type NavContext } from "$lib/config/nav";
  import { projectSections } from "$lib/stores/project-sections.svelte";
  import type { Project } from "$lib/api/schemas";
  import * as m from "$lib/paraglide/messages";
  import NavItem from "./nav-item.svelte";

  // プロジェクト 1 件分の開閉メニュー（Slack のチャンネル相当）。プロジェクト名クリックで配下メニューを開閉。
  // スター付与・セクションへの割り当てを行内のアクション（星ボタン / ⋯ メニュー）で操作する。
  let {
    project,
    orgSlug,
    active,
    onNewSection,
  }: {
    project: Project;
    orgSlug: string;
    active: boolean;
    /** 「新規セクションへ移動」選択時に親へ通知（命名ダイアログを開き、作成後にこの project を割り当てる）。 */
    onNewSection: (projectId: string) => void;
  } = $props();

  const ctx: NavContext = $derived({ orgSlug, projectSlug: project.slug, projectSelected: true });

  // アクティブ（選択中）プロジェクトは展開、それ以外は折りたたみで開始。ナビゲーションで切り替わったら追従。
  let open = $state(false);
  $effect(() => {
    if (active) open = true;
  });

  const starred = $derived(projectSections.isStarred(orgSlug, project.id));
  const sections = $derived(projectSections.sections(orgSlug));
  const currentSection = $derived(projectSections.sectionOf(orgSlug, project.id));
</script>

<Collapsible.Root bind:open>
  <div
    class={cn(
      "group flex h-9 items-center rounded-md pr-1 transition-colors hover:bg-accent/50",
      active && "bg-accent/60",
    )}
  >
    <button
      type="button"
      onclick={() => (open = !open)}
      class="flex h-full min-w-0 flex-1 items-center gap-2 px-2.5 text-left text-sm"
      aria-expanded={open}
    >
      <span
        class={cn(
          "flex size-6 shrink-0 items-center justify-center rounded",
          active ? "bg-debt-knowledge/15 text-debt-knowledge" : "text-muted-foreground",
        )}
      >
        <FolderGit2 class="size-4" />
      </span>
      <span class={cn("min-w-0 flex-1 truncate", active ? "font-medium text-foreground" : "text-muted-foreground")}>
        {project.name}
      </span>
      <ChevronDown class={cn("size-4 shrink-0 text-muted-foreground transition-transform", !open && "-rotate-90")} />
    </button>

    <!-- スター: 付与済みは常時表示、未付与はホバーで表示 -->
    <button
      type="button"
      onclick={() => projectSections.toggleStar(orgSlug, project.id)}
      aria-label={starred ? m.project_unstar() : m.project_star()}
      title={starred ? m.project_unstar() : m.project_star()}
      class={cn(
        "rounded p-1 hover:text-foreground",
        starred ? "text-amber-500 opacity-100" : "text-muted-foreground opacity-0 group-hover:opacity-100",
      )}
    >
      <Star class={cn("size-3.5", starred && "fill-current")} />
    </button>

    <!-- ⋯ メニュー: スター切替 / セクションへ移動 -->
    <DropdownMenu.Root>
      <DropdownMenu.Trigger>
        {#snippet child({ props })}
          <button
            {...props}
            aria-label={m.project_actions()}
            title={m.project_actions()}
            class="rounded p-1 text-muted-foreground opacity-0 group-hover:opacity-100 hover:text-foreground data-[state=open]:opacity-100"
          >
            <MoreHorizontal class="size-4" />
          </button>
        {/snippet}
      </DropdownMenu.Trigger>
      <DropdownMenu.Content align="start" class="w-56">
        <DropdownMenu.Item onSelect={() => projectSections.toggleStar(orgSlug, project.id)}>
          <Star class={cn("size-4", starred && "fill-current text-amber-500")} />
          <span>{starred ? m.project_unstar() : m.project_star()}</span>
        </DropdownMenu.Item>
        <DropdownMenu.Separator />
        <DropdownMenu.Label>{m.project_move_to_section()}</DropdownMenu.Label>
        <DropdownMenu.Item onSelect={() => projectSections.assign(orgSlug, project.id, null)}>
          <Check class={cn("size-4", currentSection !== null && "opacity-0")} />
          <span>{m.nav_projects()}</span>
        </DropdownMenu.Item>
        {#each sections as s (s.id)}
          <DropdownMenu.Item onSelect={() => projectSections.assign(orgSlug, project.id, s.id)}>
            <Check class={cn("size-4", currentSection !== s.id && "opacity-0")} />
            <span class="truncate">{s.name}</span>
          </DropdownMenu.Item>
        {/each}
        <DropdownMenu.Separator />
        <DropdownMenu.Item onSelect={() => onNewSection(project.id)}>
          <Plus class="size-4" />
          <span>{m.project_new_section()}</span>
        </DropdownMenu.Item>
      </DropdownMenu.Content>
    </DropdownMenu.Root>
  </div>

  <Collapsible.Content class="flex flex-col gap-0.5 py-0.5 pl-3.5">
    {#each allNavItems as item (item.id)}
      <NavItem {item} {ctx} showPill={active} />
    {/each}
  </Collapsible.Content>
</Collapsible.Root>
