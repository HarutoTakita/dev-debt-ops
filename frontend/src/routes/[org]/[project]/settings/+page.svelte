<script lang="ts">
  import Trash2 from "@lucide/svelte/icons/trash-2";
  import { page } from "$app/state";
  import { goto } from "$app/navigation";
  import { resolve } from "$app/paths";
  import { deleteProject, listBranches, patchProject } from "$lib/api/client";
  import type { Branch } from "$lib/api/schemas";
  import { Button } from "$lib/components/ui/button";
  import { Input } from "$lib/components/ui/input";
  import { project } from "$lib/stores/project-store.svelte";
  import * as m from "$lib/paraglide/messages";

  const orgSlug = $derived(page.params.org ?? "");
  const projectSlug = $derived(page.params.project ?? "");
  const current = $derived(project.current);

  let name = $state("");
  let branch = $state("");
  let branches = $state<Branch[]>([]);
  let saving = $state(false);
  let savedAt = $state(false);
  let error = $state<string | null>(null);
  let confirming = $state(false);

  // 現在プロジェクトが解決/更新されたら編集フィールドを同期する。
  $effect(() => {
    if (current) {
      name = current.name;
      branch = current.default_branch;
    }
  });

  // 既定ブランチをプルダウンで選べるよう、リポジトリのブランチ一覧を取得する。
  $effect(() => {
    const c = current;
    if (!c) return;
    void listBranches(c.repo_owner, c.repo_name)
      .then((r) => (branches = r.branches))
      .catch(() => (branches = []));
  });

  async function save() {
    if (!current) return;
    saving = true;
    savedAt = false;
    error = null;
    try {
      const updated = await patchProject(orgSlug, projectSlug, { name: name.trim(), default_branch: branch.trim() });
      project.setCurrent(updated);
      await project.loadList(orgSlug);
      savedAt = true;
      // slug は不変のままなので URL 遷移は不要（既定ブランチ/名前のみ変更）。
    } catch (e) {
      error = e instanceof Error ? e.message : m.project_settings_save_failed();
    } finally {
      saving = false;
    }
  }

  async function remove() {
    if (!current) return;
    error = null;
    try {
      await deleteProject(orgSlug, projectSlug);
      await project.loadList(orgSlug);
      await goto(resolve(`/${orgSlug}`));
    } catch (e) {
      error = e instanceof Error ? e.message : m.project_settings_delete_failed();
      confirming = false;
    }
  }
</script>

<svelte:head>
  <title>{m.project_settings_title()} · DevDebtOps</title>
</svelte:head>

<div class="mx-auto w-full max-w-2xl px-6 py-10">
  <h1 class="font-display text-2xl font-semibold tracking-tight">{m.project_settings_title()}</h1>

  {#if current}
    <div class="mt-6 flex flex-col gap-5">
      <label class="flex flex-col gap-1.5">
        <span class="text-sm font-medium">{m.project_settings_name_label()}</span>
        <Input bind:value={name} />
      </label>

      <label class="flex flex-col gap-1.5">
        <span class="text-sm font-medium">{m.project_settings_branch_label()}</span>
        <select
          bind:value={branch}
          class="h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm shadow-xs focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none"
        >
          {#each branches as b (b.name)}
            <option value={b.name}>{b.name}{b.is_default ? " (default)" : ""}</option>
          {/each}
          {#if !branches.some((b) => b.name === branch)}
            <option value={branch}>{branch}</option>
          {/if}
        </select>
      </label>

      <div class="flex flex-col gap-1.5">
        <span class="text-sm font-medium">{m.project_settings_repo_label()}</span>
        <p
          class="rounded-md border border-sidebar-border bg-surface-sunken px-3 py-2 font-mono text-sm text-muted-foreground"
        >
          {current.repo_full_name}
        </p>
      </div>

      {#if error}
        <p class="text-sm text-danger">{error}</p>
      {/if}

      <div class="flex items-center gap-3">
        <Button onclick={save} disabled={saving || !name.trim() || !branch.trim()}>
          {m.project_settings_save()}
        </Button>
        {#if savedAt}<span class="text-sm text-success">{m.project_settings_saved()}</span>{/if}
      </div>

      <div class="mt-6 rounded-lg border border-danger/40 p-4">
        <h2 class="font-display text-sm font-semibold text-danger">{m.project_settings_danger_title()}</h2>
        {#if confirming}
          <p class="mt-2 text-sm text-muted-foreground">{m.project_settings_delete_confirm()}</p>
          <div class="mt-3 flex items-center gap-2">
            <Button variant="destructive" size="sm" onclick={remove}>
              <Trash2 class="size-4" />
              {m.project_settings_delete()}
            </Button>
            <Button variant="ghost" size="sm" onclick={() => (confirming = false)}>{m.common_cancel()}</Button>
          </div>
        {:else}
          <div class="mt-3">
            <Button variant="outline" size="sm" onclick={() => (confirming = true)}>
              <Trash2 class="size-4" />
              {m.project_settings_delete()}
            </Button>
          </div>
        {/if}
      </div>
    </div>
  {/if}
</div>
