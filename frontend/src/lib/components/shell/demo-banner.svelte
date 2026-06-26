<script lang="ts">
  import { resolve } from "$app/paths";
  import { auth } from "$lib/stores/auth.svelte";
</script>

{#if auth.isDemo}
  <!-- ゲストデモ環境の常設バナー（issue 069）。GitHub サインインへ誘導する。 -->
  <div
    class="flex flex-wrap items-center justify-center gap-x-2 gap-y-1 border-b border-amber-300/60 bg-amber-50 px-4 py-2 text-center text-xs text-amber-900 dark:border-amber-500/30 dark:bg-amber-950/40 dark:text-amber-200"
    role="status"
  >
    <span>これはサンプルデータの<strong>デモ環境</strong>です。GitHub 連携が必要な操作は利用できません。</span>
    <a href={resolve("/login")} class="font-medium underline underline-offset-2 hover:no-underline">
      GitHub でサインイン
    </a>
    <span>すると、自分のリポジトリを解析できます。</span>
  </div>
{/if}
