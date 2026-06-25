<script lang="ts">
  import ArrowLeft from "@lucide/svelte/icons/arrow-left";
  import FolderGit2 from "@lucide/svelte/icons/folder-git-2";
  import { page } from "$app/state";
  import { goto } from "$app/navigation";
  import { resolve } from "$app/paths";
  import { createProject } from "$lib/api/client";
  import type { Repository } from "$lib/api/schemas";
  import * as Dialog from "$lib/components/ui/dialog";
  import { Button } from "$lib/components/ui/button";
  import { Input } from "$lib/components/ui/input";
  import RepoPicker from "$lib/components/repo/repo-picker.svelte";
  import { project } from "$lib/stores/project-store.svelte";
  import { repo } from "$lib/stores/repo-store.svelte";
  import { onboarding } from "$lib/stores/onboarding-store.svelte";
  import { projectCreate } from "$lib/stores/project-create.svelte";
  import * as m from "$lib/paraglide/messages";

  // 新規プロジェクト作成モーダル（別ページの代替）。リポジトリ選択 → 名前入力 → 作成 → 当該プロジェクトの
  // ダッシュボードへ遷移。グローバル store（projectCreate）で開閉する。
  const orgSlug = $derived(page.params.org ?? "");

  let selectedRepo = $state<Repository | null>(null);
  let name = $state("");
  let submitting = $state(false);
  let error = $state<string | null>(null);

  function pickRepo(r: Repository) {
    selectedRepo = r;
    name = r.name;
    error = null;
  }
  function reset() {
    selectedRepo = null;
    name = "";
    error = null;
  }

  // 閉じたら入力状態をクリアして次回まっさらにする。
  $effect(() => {
    if (!projectCreate.open) {
      selectedRepo = null;
      name = "";
      error = null;
      submitting = false;
    }
  });

  async function submit() {
    if (!selectedRepo || !name.trim()) return;
    submitting = true;
    error = null;
    try {
      const created = await createProject(orgSlug, name.trim(), selectedRepo);
      // 遷移前に現在プロジェクト/リポジトリを確定（接続済みダッシュボードへ着地・サイドバー展開）。
      project.setCurrent(created);
      repo.connect(selectedRepo);
      await project.loadList(orgSlug);
      if (project.list.length <= 1) onboarding.requestAutoStart(orgSlug);
      projectCreate.open = false;
      await goto(resolve(`/${orgSlug}/${created.slug}`));
    } catch (e) {
      error = e instanceof Error ? e.message : m.project_create_failed();
      submitting = false;
    }
  }
</script>

<Dialog.Root bind:open={projectCreate.open}>
  <Dialog.Content class="max-h-[85vh] gap-4 overflow-y-auto sm:max-w-lg">
    <Dialog.Header>
      <Dialog.Title>{m.project_create_title()}</Dialog.Title>
      {#if selectedRepo}
        <Dialog.Description>{m.project_create_name_label()}</Dialog.Description>
      {/if}
    </Dialog.Header>

    {#if !selectedRepo}
      <RepoPicker onselect={pickRepo} />
    {:else}
      <div class="flex flex-col gap-5">
        <div class="flex items-center gap-2 rounded-md border border-sidebar-border bg-surface-sunken px-3 py-2.5">
          <FolderGit2 class="size-4 shrink-0 text-debt-knowledge" />
          <span class="min-w-0 flex-1 truncate font-mono text-sm">{selectedRepo.full_name}</span>
          <button
            type="button"
            onclick={reset}
            class="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft class="size-3.5" />
            {m.project_create_back()}
          </button>
        </div>

        <label class="flex flex-col gap-1.5">
          <span class="text-sm font-medium">{m.project_create_name_label()}</span>
          <Input bind:value={name} />
        </label>

        {#if error}
          <p class="text-sm text-danger">{error}</p>
        {/if}

        <div>
          <Button onclick={submit} disabled={submitting || !name.trim()}>
            {submitting ? m.project_create_submitting() : m.project_create_submit()}
          </Button>
        </div>
      </div>
    {/if}
  </Dialog.Content>
</Dialog.Root>
