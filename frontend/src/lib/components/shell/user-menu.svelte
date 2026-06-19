<script lang="ts">
  import LogOut from "@lucide/svelte/icons/log-out";
  import SunMoon from "@lucide/svelte/icons/sun-moon";
  import { goto } from "$app/navigation";
  import { resolve } from "$app/paths";
  import { toggleMode } from "mode-watcher";
  import { apiFetch } from "$lib/api/client";
  import { auth } from "$lib/stores/auth.svelte";
  import * as Avatar from "$lib/components/ui/avatar";
  import * as DropdownMenu from "$lib/components/ui/dropdown-menu";
  import * as m from "$lib/paraglide/messages";

  const email = $derived(auth.user?.email ?? "");
  const initial = $derived(email ? email[0].toUpperCase() : "?");

  async function logout() {
    await apiFetch("/api/v1/auth/access/logout", { method: "POST" });
    auth.clear();
    goto(resolve("/login"));
  }
</script>

<DropdownMenu.Root>
  <DropdownMenu.Trigger
    class="flex size-8 items-center justify-center rounded-full outline-none focus-visible:ring-2 focus-visible:ring-ring"
    aria-label={email}
  >
    <Avatar.Root class="size-8">
      <Avatar.Fallback class="bg-debt-knowledge/20 text-foreground">{initial}</Avatar.Fallback>
    </Avatar.Root>
  </DropdownMenu.Trigger>
  <DropdownMenu.Content align="end" class="w-56">
    <DropdownMenu.Label class="truncate text-xs font-normal text-muted-foreground">{email}</DropdownMenu.Label>
    <DropdownMenu.Separator />
    <DropdownMenu.Item onSelect={() => toggleMode()}>
      <SunMoon class="size-4" />
      <span>{m.shell_toggle_theme()}</span>
    </DropdownMenu.Item>
    <DropdownMenu.Separator />
    <DropdownMenu.Item onSelect={logout}>
      <LogOut class="size-4" />
      <span>{m.shell_logout()}</span>
    </DropdownMenu.Item>
  </DropdownMenu.Content>
</DropdownMenu.Root>
