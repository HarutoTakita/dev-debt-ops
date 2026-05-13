<script lang="ts">
  import { goto } from "$app/navigation";
  import { resolve } from "$app/paths";
  import { page } from "$app/state";
  import { apiFetch } from "$lib/api/client";
  import { auth } from "$lib/stores/auth.svelte";

  let { children } = $props();

  const orgSlug = $derived(page.params.org);

  async function handleLogout() {
    await apiFetch("/api/v1/auth/access/logout", { method: "POST" });
    auth.clear();
    goto(resolve("/login"));
  }
</script>

<div class="flex h-screen flex-col">
  <header class="flex shrink-0 items-center justify-between border-b px-4 py-2">
    <span class="font-semibold">{orgSlug}</span>
    <div class="flex items-center gap-4 text-sm">
      <span class="text-muted-foreground">{auth.user?.email}</span>
      <button onclick={handleLogout} class="hover:underline">ログアウト</button>
    </div>
  </header>
  <main class="flex-1 overflow-hidden">
    {@render children()}
  </main>
</div>
