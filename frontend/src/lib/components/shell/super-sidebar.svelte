<script lang="ts">
  import FolderGit2 from "@lucide/svelte/icons/folder-git-2";
  import Plus from "@lucide/svelte/icons/plus";
  import ChevronDown from "@lucide/svelte/icons/chevron-down";
  import Star from "@lucide/svelte/icons/star";
  import MoreHorizontal from "@lucide/svelte/icons/more-horizontal";
  import Pencil from "@lucide/svelte/icons/pencil";
  import Trash2 from "@lucide/svelte/icons/trash-2";
  import Hash from "@lucide/svelte/icons/hash";
  import LayoutGrid from "@lucide/svelte/icons/layout-grid";
  import CircleHelp from "@lucide/svelte/icons/circle-help";
  import { page } from "$app/state";
  import { goto } from "$app/navigation";
  import { resolve } from "$app/paths";
  import { cn } from "$lib/utils";
  import * as Tooltip from "$lib/components/ui/tooltip";
  import * as DropdownMenu from "$lib/components/ui/dropdown-menu";
  import * as Dialog from "$lib/components/ui/dialog";
  import { Input } from "$lib/components/ui/input";
  import Skeleton from "$lib/components/ui-ext/skeleton.svelte";
  import { sidebar } from "$lib/stores/sidebar-store.svelte";
  import { project } from "$lib/stores/project-store.svelte";
  import {
    projectSections,
    STARRED_KEY,
    DEFAULT_KEY,
    SECTION_ICON_COLORS,
    type ProjectSection,
  } from "$lib/stores/project-sections.svelte";
  import type { Project } from "$lib/api/schemas";
  import type { Pathname } from "$app/types";
  import * as m from "$lib/paraglide/messages";
  import ProjectNavGroup from "./project-nav-group.svelte";

  const orgSlug = $derived(page.params.org ?? "");
  const currentId = $derived(project.current?.id);
  // ヘルプページ（オンボーディングガイド再生）への導線。現在プロジェクトがあるときのみ表示。
  const helpPath: Pathname | null = $derived(
    project.current ? (`/${orgSlug}/${project.current.slug}/help` as Pathname) : null,
  );

  // org の全プロジェクトをサイドバーに同時表示。一覧未取得（直リンク到達など）でも現在プロジェクトの
  // メニューは即使えるよう、フォールバックで current を出す。
  const projects = $derived(project.list.length > 0 ? project.list : project.current ? [project.current] : []);

  // org が変わったら一覧をロード（スイッチャー無しでも全件出すため）。org のみ追跡し再実行ループを避ける。
  let loadedOrg: string | null = null;
  $effect(() => {
    const org = page.params.org ?? "";
    if (org && org !== loadedOrg) {
      loadedOrg = org;
      project.loadList(org);
    }
  });

  // 表示グループ: スター付き → ユーザー定義セクション（順序保持）→ 既定（未分類）。
  // 各プロジェクトはスター優先で 1 グループにのみ現れる。空のセクションも管理用に表示する。
  type Group = { key: string; label: string; section: ProjectSection | null; items: Project[] };
  const groups = $derived.by<Group[]>(() => {
    const starred = projects.filter((p) => projectSections.isStarred(orgSlug, p.id));
    const custom = projectSections.sections(orgSlug).map((s) => ({
      key: s.id,
      label: s.name,
      section: s,
      items: projects.filter(
        (p) => !projectSections.isStarred(orgSlug, p.id) && projectSections.sectionOf(orgSlug, p.id) === s.id,
      ),
    }));
    const fallback = projects.filter(
      (p) => !projectSections.isStarred(orgSlug, p.id) && projectSections.sectionOf(orgSlug, p.id) === null,
    );
    return [
      ...(starred.length > 0 ? [{ key: STARRED_KEY, label: m.nav_starred(), section: null, items: starred }] : []),
      ...custom,
      { key: DEFAULT_KEY, label: m.nav_projects(), section: null, items: fallback },
    ];
  });

  // セクション命名ダイアログ（作成 / 改名）。
  let dialogOpen = $state(false);
  let dialogMode = $state<"create" | "rename">("create");
  let dialogName = $state("");
  let dialogSectionId = $state<string | null>(null);
  let pendingProjectId = $state<string | null>(null);

  function openCreateSection(projectId: string | null = null) {
    dialogMode = "create";
    dialogName = "";
    dialogSectionId = null;
    pendingProjectId = projectId;
    dialogOpen = true;
  }
  function openRenameSection(section: ProjectSection) {
    dialogMode = "rename";
    dialogName = section.name;
    dialogSectionId = section.id;
    pendingProjectId = null;
    dialogOpen = true;
  }
  function submitDialog() {
    const name = dialogName.trim();
    if (!name) return;
    if (dialogMode === "create") {
      const id = projectSections.createSection(orgSlug, name);
      if (pendingProjectId) projectSections.assign(orgSlug, pendingProjectId, id);
    } else if (dialogSectionId) {
      projectSections.renameSection(orgSlug, dialogSectionId, name);
    }
    dialogOpen = false;
  }

  function newProject() {
    goto(resolve(`/${orgSlug}/projects/new`));
  }

  // ドラッグ&ドロップでプロジェクトをグループ間移動。dragOverKey はドロップ先のハイライト用。
  let dragOverKey = $state<string | null>(null);
  function onDrop(e: DragEvent, groupKey: string) {
    e.preventDefault();
    const id = e.dataTransfer?.getData("text/plain");
    dragOverKey = null;
    if (id) projectSections.moveToGroup(orgSlug, id, groupKey);
  }

  const skeletonRows = Array.from({ length: 4 }, (_v, i) => i);
</script>

<Tooltip.Provider delayDuration={0}>
  <nav class="flex h-full flex-col overflow-y-auto p-2" aria-label="primary">
    <div class="flex flex-1 flex-col gap-1">
      {#if projects.length > 0}
        {#if sidebar.collapsed}
          <!-- 折りたたみ時はサブメニューを畳めないため、各プロジェクトの Overview へのアイコンリンクにする。 -->
          <div class="flex flex-col gap-0.5">
            {#each projects as p (p.id)}
              <Tooltip.Root>
                <Tooltip.Trigger>
                  {#snippet child({ props })}
                    <a
                      {...props}
                      href={resolve(`/${orgSlug}/${p.slug}`)}
                      aria-current={p.id === currentId ? "page" : undefined}
                      class={cn(
                        "flex h-9 items-center justify-center rounded-md transition-colors",
                        p.id === currentId
                          ? "bg-accent text-foreground"
                          : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
                      )}
                    >
                      <FolderGit2 class="size-4" />
                    </a>
                  {/snippet}
                </Tooltip.Trigger>
                <Tooltip.Content side="right">{p.name}</Tooltip.Content>
              </Tooltip.Root>
            {/each}
          </div>
        {:else}
          {#each groups as group (group.key)}
            {@const collapsed = projectSections.isCollapsed(orgSlug, group.key)}
            <!-- グループ全体がドロップ先（ここに落とすとそのグループへ移動）。 -->
            <section
              role="group"
              aria-label={group.label}
              ondragover={(e) => {
                e.preventDefault();
                if (e.dataTransfer) e.dataTransfer.dropEffect = "move";
                dragOverKey = group.key;
              }}
              ondragleave={(e) => {
                if (!e.currentTarget.contains(e.relatedTarget as Node | null)) dragOverKey = null;
              }}
              ondrop={(e) => onDrop(e, group.key)}
              class={cn("rounded-md", dragOverKey === group.key && "bg-accent/40 ring-1 ring-debt-knowledge/40")}
            >
              <div class="group/section flex items-center gap-1 px-1 pt-2 pb-0.5">
                <button
                  type="button"
                  onclick={() => projectSections.toggleCollapsed(orgSlug, group.key)}
                  class="flex min-w-0 flex-1 items-center gap-1 text-xs font-medium tracking-wide text-muted-foreground uppercase hover:text-foreground"
                >
                  {#if group.key === STARRED_KEY}
                    <Star class="size-3 shrink-0 fill-current text-amber-500" />
                  {:else if group.section}
                    <Hash class={cn("size-3 shrink-0", SECTION_ICON_COLORS[group.section.color ?? 0])} />
                  {:else}
                    <LayoutGrid class="size-3 shrink-0 text-debt-knowledge" />
                  {/if}
                  <span class="truncate">{group.label}</span>
                  <ChevronDown class={cn("size-3 shrink-0 transition-transform", collapsed && "-rotate-90")} />
                </button>
                {#if group.section}
                  <DropdownMenu.Root>
                    <DropdownMenu.Trigger>
                      {#snippet child({ props })}
                        <button
                          {...props}
                          aria-label={m.section_actions()}
                          title={m.section_actions()}
                          class="rounded p-0.5 text-muted-foreground opacity-0 group-hover/section:opacity-100 hover:text-foreground data-[state=open]:opacity-100"
                        >
                          <MoreHorizontal class="size-3.5" />
                        </button>
                      {/snippet}
                    </DropdownMenu.Trigger>
                    <DropdownMenu.Content align="start" class="w-44">
                      <DropdownMenu.Item onSelect={() => group.section && openRenameSection(group.section)}>
                        <Pencil class="size-4" />
                        <span>{m.section_rename()}</span>
                      </DropdownMenu.Item>
                      <DropdownMenu.Item
                        onSelect={() => group.section && projectSections.deleteSection(orgSlug, group.section.id)}
                      >
                        <Trash2 class="size-4" />
                        <span>{m.section_delete()}</span>
                      </DropdownMenu.Item>
                    </DropdownMenu.Content>
                  </DropdownMenu.Root>
                {/if}
              </div>
              {#if !collapsed}
                <div class="flex flex-col gap-0.5 pb-0.5">
                  {#each group.items as p (p.id)}
                    <ProjectNavGroup
                      project={p}
                      {orgSlug}
                      active={p.id === currentId}
                      onNewSection={openCreateSection}
                    />
                  {/each}
                  {#if group.items.length === 0}
                    <p class="px-2.5 py-1 text-xs text-muted-foreground/70">{m.section_empty()}</p>
                  {/if}
                </div>
              {/if}
            </section>
          {/each}
        {/if}
      {:else if project.loading}
        <div class="flex flex-col gap-1 px-1" aria-busy="true">
          {#each skeletonRows as i (i)}
            <div class="flex items-center gap-2 px-1.5 py-1.5">
              <Skeleton class="size-5 rounded" />
              {#if !sidebar.collapsed}<Skeleton class="h-4 flex-1" />{/if}
            </div>
          {/each}
        </div>
      {:else if project.error !== null && !sidebar.collapsed}
        <div class="flex flex-col items-start gap-2 px-2.5 py-2">
          <p class="text-xs text-destructive">{m.project_switcher_error()}</p>
          <button
            type="button"
            onclick={() => project.loadList(orgSlug)}
            class="rounded-md border px-2.5 py-1 text-xs hover:bg-accent/50"
          >
            {m.common_retry()}
          </button>
        </div>
      {:else if !sidebar.collapsed}
        <p class="px-2.5 py-2 text-xs leading-relaxed text-muted-foreground">{m.project_switcher_hint()}</p>
      {/if}
    </div>

    <!-- 一番下: 新規プロジェクト作成 -->
    <div class="mt-1 border-t border-sidebar-border pt-2">
      {#if sidebar.collapsed}
        <Tooltip.Root>
          <Tooltip.Trigger>
            {#snippet child({ props })}
              <button
                {...props}
                onclick={newProject}
                aria-label={m.project_switcher_new()}
                class="flex h-9 w-full items-center justify-center rounded-md text-debt-code hover:bg-accent/50"
              >
                <Plus class="size-4" />
              </button>
            {/snippet}
          </Tooltip.Trigger>
          <Tooltip.Content side="right">{m.project_switcher_new()}</Tooltip.Content>
        </Tooltip.Root>
      {:else}
        <button
          type="button"
          onclick={newProject}
          class="flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-sm font-medium text-debt-code transition-colors hover:bg-accent/50"
        >
          <Plus class="size-4" />
          <span>{m.project_switcher_new()}</span>
        </button>
      {/if}
    </div>

    <!-- 一番下: ヘルプ（オンボーディングガイドを再生できる、issue 066） -->
    {#if helpPath}
      <div class="mt-1">
        {#if sidebar.collapsed}
          <Tooltip.Root>
            <Tooltip.Trigger>
              {#snippet child({ props })}
                <a
                  {...props}
                  href={resolve(helpPath)}
                  data-tour="help"
                  aria-label={m.nav_help()}
                  class="flex h-9 w-full items-center justify-center rounded-md text-muted-foreground hover:bg-accent/50 hover:text-foreground"
                >
                  <CircleHelp class="size-4" />
                </a>
              {/snippet}
            </Tooltip.Trigger>
            <Tooltip.Content side="right">{m.nav_help()}</Tooltip.Content>
          </Tooltip.Root>
        {:else}
          <a
            href={resolve(helpPath)}
            data-tour="help"
            class="flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-accent/50 hover:text-foreground"
          >
            <CircleHelp class="size-4" />
            <span>{m.nav_help()}</span>
          </a>
        {/if}
      </div>
    {/if}
  </nav>
</Tooltip.Provider>

<Dialog.Root bind:open={dialogOpen}>
  <Dialog.Content class="sm:max-w-md">
    <Dialog.Header>
      <Dialog.Title>{dialogMode === "create" ? m.section_create_title() : m.section_rename_title()}</Dialog.Title>
    </Dialog.Header>
    <form
      onsubmit={(e) => {
        e.preventDefault();
        submitDialog();
      }}
      class="flex flex-col gap-4"
    >
      <Input bind:value={dialogName} placeholder={m.section_name_placeholder()} autofocus />
      <Dialog.Footer>
        <button
          type="button"
          onclick={() => (dialogOpen = false)}
          class="rounded-md border px-3 py-1.5 text-sm hover:bg-accent/50"
        >
          {m.common_cancel()}
        </button>
        <button
          type="submit"
          disabled={dialogName.trim().length === 0}
          class="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
        >
          {m.common_save()}
        </button>
      </Dialog.Footer>
    </form>
  </Dialog.Content>
</Dialog.Root>
