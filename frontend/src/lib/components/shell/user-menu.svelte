<script lang="ts">
  import LogOut from "@lucide/svelte/icons/log-out";
  import SunMoon from "@lucide/svelte/icons/sun-moon";
  import Shield from "@lucide/svelte/icons/shield";
  import CircleUser from "@lucide/svelte/icons/circle-user";
  import Check from "@lucide/svelte/icons/check";
  import { goto } from "$app/navigation";
  import { resolve } from "$app/paths";
  import { toggleMode } from "mode-watcher";
  import { apiFetch } from "$lib/api/client";
  import { auth } from "$lib/stores/auth.svelte";
  import { cn } from "$lib/utils";
  import { getLocale, locales, setLocale, type Locale } from "$lib/paraglide/runtime";
  import * as Avatar from "$lib/components/ui/avatar";
  import * as DropdownMenu from "$lib/components/ui/dropdown-menu";
  import * as m from "$lib/paraglide/messages";

  const email = $derived(auth.user?.email ?? "");
  const initial = $derived(email ? email[0].toUpperCase() : "?");

  // 言語切替。ロケール名は自称語（翻訳しない）。setLocale は Paraglide が再読込して全体を再描画する。
  const localeNames: Record<Locale, string> = {
    ja: "日本語",
    en: "English",
    zh: "中文",
    ko: "한국어",
    es: "Español",
    de: "Deutsch",
  };
  const currentLocale = getLocale();

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
    <DropdownMenu.Item onSelect={() => goto(resolve("/account"))}>
      <CircleUser class="size-4" />
      <span>{m.shell_account()}</span>
    </DropdownMenu.Item>
    <DropdownMenu.Separator />
    {#if auth.isAdmin}
      <DropdownMenu.Item onSelect={() => goto(resolve("/admin"))}>
        <Shield class="size-4" />
        <span>{m.shell_user_admin()}</span>
      </DropdownMenu.Item>
      <DropdownMenu.Separator />
    {/if}
    <DropdownMenu.Item onSelect={() => toggleMode()}>
      <SunMoon class="size-4" />
      <span>{m.shell_toggle_theme()}</span>
    </DropdownMenu.Item>
    <DropdownMenu.Separator />
    <DropdownMenu.Label class="text-xs font-normal text-muted-foreground">{m.shell_language()}</DropdownMenu.Label>
    {#each locales as loc (loc)}
      <DropdownMenu.Item onSelect={() => setLocale(loc)}>
        <Check class={cn("size-4", currentLocale !== loc && "opacity-0")} />
        <span>{localeNames[loc]}</span>
      </DropdownMenu.Item>
    {/each}
    <DropdownMenu.Separator />
    <DropdownMenu.Item onSelect={logout}>
      <LogOut class="size-4" />
      <span>{m.shell_logout()}</span>
    </DropdownMenu.Item>
  </DropdownMenu.Content>
</DropdownMenu.Root>
