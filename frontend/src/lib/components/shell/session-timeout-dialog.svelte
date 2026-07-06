<script lang="ts">
  import Clock from "@lucide/svelte/icons/clock";
  import * as Dialog from "$lib/components/ui/dialog";
  import { Button } from "$lib/components/ui/button";
  import { auth } from "$lib/stores/auth.svelte";
  import { sessionTimeout } from "$lib/stores/session-timeout.svelte";
  import * as m from "$lib/paraglide/messages";

  // 無操作セッションタイムアウトの警告モーダル（残り 5 分で表示、カウントダウン）。
  // 表示状態は sessionTimeout.showWarning に従う。閉じる操作（Esc/外側/ボタン）は「操作を続ける」= 延長扱い。
  const remaining = $derived.by(() => {
    const s = Math.max(0, Math.ceil(sessionTimeout.remainingMs / 1000));
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  });
</script>

<Dialog.Root
  open={sessionTimeout.showWarning}
  onOpenChange={(o) => {
    // Esc / 外側クリックで閉じたら延長（＝操作あり）。ただし停止(ログアウト)由来のクローズでは延長しない。
    if (!o && sessionTimeout.active) sessionTimeout.extend();
  }}
>
  <Dialog.Content class="sm:max-w-md" data-tour="session-timeout">
    <Dialog.Header>
      <Dialog.Title class="flex items-center gap-2">
        <Clock class="size-4 text-destructive" />
        {m.session_timeout_title()}
      </Dialog.Title>
      <Dialog.Description>{m.session_timeout_desc({ time: remaining })}</Dialog.Description>
    </Dialog.Header>
    <Dialog.Footer>
      <Button variant="outline" onclick={() => auth.logout()}>{m.session_timeout_logout()}</Button>
      <Button onclick={() => sessionTimeout.extend()}>{m.session_timeout_continue()}</Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>
