<script lang="ts">
  import { Command } from "bits-ui";
  import Search from "@lucide/svelte/icons/search";
  import Folder from "@lucide/svelte/icons/folder";
  import SunMoon from "@lucide/svelte/icons/sun-moon";
  import { goto } from "$app/navigation";
  import { resolve } from "$app/paths";
  import { page } from "$app/state";
  import type { Pathname } from "$app/types";
  import { toggleMode } from "mode-watcher";
  import * as Dialog from "$lib/components/ui/dialog";
  import { allNavItems, type NavContext } from "$lib/config/nav";
  import { project } from "$lib/stores/project-store.svelte";
  import * as m from "$lib/paraglide/messages";

  // ⌘K で開くコマンドパレット。ページ移動（現在プロジェクトのセクション）・プロジェクト切替・
  // 全般操作（テーマ切替）を 1 か所で検索/実行する。bits-ui Command の組み込みフィルタで絞り込む。
  let { open = $bindable(false) }: { open?: boolean } = $props();

  const orgSlug = $derived(page.params.org ?? "");
  const projectSlug = $derived(page.params.project ?? "");
  const projectSelected = $derived(!!page.params.project);
  const ctx = $derived<NavContext>({ orgSlug, projectSlug, projectSelected });

  // 現在のプロジェクト以外を切替候補に出す。enabled が定義された項目は条件を満たすもののみ。
  const navItems = $derived(allNavItems.filter((i) => (i.enabled ? i.enabled(ctx) : true)));
  const otherProjects = $derived(project.list.filter((p) => p.slug !== projectSlug));

  // パレットを開いたとき、まだ一覧が無ければ取得（切替候補を埋める）。loadedOrg は非リアクティブな
  // ガードで、空 org でも 1 回だけ試行して再フェッチのループを防ぐ。
  let loadedOrg = "";
  $effect(() => {
    if (open && orgSlug && orgSlug !== loadedOrg && project.list.length === 0 && !project.loading) {
      loadedOrg = orgSlug;
      void project.loadList(orgSlug);
    }
  });

  function run(action: () => void) {
    open = false;
    action();
  }

  function navTo(path: Pathname) {
    run(() => void goto(resolve(path)));
  }
</script>

<Dialog.Root bind:open>
  <Dialog.Content class="overflow-hidden p-0 sm:max-w-lg" showCloseButton={false}>
    <Dialog.Title class="sr-only">{m.shell_command_palette()}</Dialog.Title>
    <Dialog.Description class="sr-only">{m.command_placeholder()}</Dialog.Description>
    <Command.Root class="flex w-full flex-col">
      <div class="flex items-center gap-2 border-b border-border px-3">
        <Search class="size-4 shrink-0 text-muted-foreground" />
        <Command.Input
          placeholder={m.command_placeholder()}
          class="flex h-11 w-full bg-transparent py-3 text-sm outline-none placeholder:text-muted-foreground"
        />
      </div>

      <Command.List class="max-h-80 overflow-y-auto overflow-x-hidden p-1">
        <Command.Empty class="py-6 text-center text-sm text-muted-foreground">
          {m.command_empty()}
        </Command.Empty>

        {#if projectSelected}
          <Command.Group>
            <Command.GroupHeading class="px-2 py-1.5 text-xs font-medium text-muted-foreground">
              {m.command_group_navigation()}
            </Command.GroupHeading>
            <Command.GroupItems>
              {#each navItems as item (item.id)}
                <Command.Item
                  value={`nav:${item.id}`}
                  keywords={[item.label(), item.id]}
                  onSelect={() => navTo(item.route(ctx))}
                  class="flex cursor-pointer items-center gap-2 rounded-md px-2 py-2 text-sm outline-none data-selected:bg-accent data-selected:text-accent-foreground"
                >
                  <item.icon class="size-4 shrink-0 text-muted-foreground" />
                  <span class="truncate">{item.label()}</span>
                </Command.Item>
              {/each}
            </Command.GroupItems>
          </Command.Group>
        {/if}

        {#if otherProjects.length > 0}
          <Command.Separator class="my-1 h-px bg-border" />
          <Command.Group>
            <Command.GroupHeading class="px-2 py-1.5 text-xs font-medium text-muted-foreground">
              {m.command_group_projects()}
            </Command.GroupHeading>
            <Command.GroupItems>
              {#each otherProjects as p (p.id)}
                <Command.Item
                  value={`project:${p.slug}`}
                  keywords={[p.name, p.repo_full_name, p.slug]}
                  onSelect={() => navTo(`/${orgSlug}/${p.slug}`)}
                  class="flex cursor-pointer items-center gap-2 rounded-md px-2 py-2 text-sm outline-none data-selected:bg-accent data-selected:text-accent-foreground"
                >
                  <Folder class="size-4 shrink-0 text-muted-foreground" />
                  <span class="truncate">{p.name}</span>
                  <span class="ml-auto truncate pl-2 text-xs text-muted-foreground">{p.repo_full_name}</span>
                </Command.Item>
              {/each}
            </Command.GroupItems>
          </Command.Group>
        {/if}

        <Command.Separator class="my-1 h-px bg-border" />
        <Command.Group>
          <Command.GroupHeading class="px-2 py-1.5 text-xs font-medium text-muted-foreground">
            {m.command_group_general()}
          </Command.GroupHeading>
          <Command.GroupItems>
            <Command.Item
              value="general:theme"
              keywords={["theme", "dark", "light", "テーマ", "ダーク", "ライト"]}
              onSelect={() => run(() => toggleMode())}
              class="flex cursor-pointer items-center gap-2 rounded-md px-2 py-2 text-sm outline-none data-selected:bg-accent data-selected:text-accent-foreground"
            >
              <SunMoon class="size-4 shrink-0 text-muted-foreground" />
              <span class="truncate">{m.shell_toggle_theme()}</span>
            </Command.Item>
          </Command.GroupItems>
        </Command.Group>
      </Command.List>
    </Command.Root>
  </Dialog.Content>
</Dialog.Root>
