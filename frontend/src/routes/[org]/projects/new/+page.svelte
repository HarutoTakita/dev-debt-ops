<script lang="ts">
  import ArrowLeft from "@lucide/svelte/icons/arrow-left";
  import FolderGit2 from "@lucide/svelte/icons/folder-git-2";
  import { page } from "$app/state";
  import { goto } from "$app/navigation";
  import { resolve } from "$app/paths";
  import { createProject } from "$lib/api/client";
  import type { Repository } from "$lib/api/schemas";
  import { Button } from "$lib/components/ui/button";
  import { Input } from "$lib/components/ui/input";
  import RepoPicker from "$lib/components/repo/repo-picker.svelte";
  import { project } from "$lib/stores/project-store.svelte";
  import * as m from "$lib/paraglide/messages";

  const orgSlug = $derived(page.params.org ?? "");

  let selectedRepo = $state<Repository | null>(null);
  let name = $state("");
  let submitting = $state(false);
  let error = $state<string | null>(null);

  function pickRepo(repo: Repository) {
    selectedRepo = repo;
    name = repo.name;
    error = null;
  }

  function reset() {
    selectedRepo = null;
    name = "";
    error = null;
  }

  async function submit() {
    if (!selectedRepo || !name.trim()) return;
    submitting = true;
    error = null;
    try {
      const created = await createProject(orgSlug, name.trim(), selectedRepo);
      await project.loadList(orgSlug);
      await goto(resolve(`/${orgSlug}/${created.slug}`));
    } catch (e) {
      error = e instanceof Error ? e.message : m.project_create_failed();
      submitting = false;
    }
  }
</script>

<svelte:head>
  <title>{m.project_create_title()} · Rosetta</title>
</svelte:head>

<div class="mx-auto w-full max-w-2xl px-6 py-10">
  <h1 class="font-display text-2xl font-semibold tracking-tight">{m.project_create_title()}</h1>

  {#if !selectedRepo}
    <p class="mt-1 text-sm text-muted-foreground">{m.project_create_pick_repo()}</p>
    <div class="mt-6">
      <RepoPicker onselect={pickRepo} />
    </div>
  {:else}
    <div class="mt-6 flex flex-col gap-5">
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
</div>
