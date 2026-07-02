<script lang="ts">
  import LoginGraphCanvas from "./login-graph-canvas.svelte";
  import Logo from "$lib/components/logo.svelte";

  // ログイン中（OAuth コールバック）のローディング・スプラッシュ。背景は共通の動くノード‐リンクグラフ
  // （login-graph-canvas, 参考LP 参照）に刷新し、中央にアプリアイコン（favicon.svg = Logo）と
  // 「DevDebtOps」・メッセージを重ねる。
  let { message = "" }: { message?: string } = $props();
</script>

<div class="splash">
  <LoginGraphCanvas />

  <div class="content">
    <Logo class="size-16 drop-shadow-[0_0_18px_rgba(34,184,196,0.35)]" />
    <h1 class="name">DevDebtOps</h1>
    {#if message}
      <p class="msg">{message}</p>
    {/if}
  </div>
</div>

<style>
  .splash {
    position: fixed;
    inset: 0;
    z-index: 50;
    display: grid;
    place-items: center;
    overflow: hidden;
    background: #080d1a;
  }
  .content {
    position: relative;
    z-index: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.75rem;
    animation: rise 0.6s ease-out both;
  }
  @keyframes rise {
    from {
      opacity: 0;
      transform: translateY(8px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }
  .name {
    font-size: 2.25rem;
    font-weight: 700;
    letter-spacing: -0.01em;
    color: #f1f5f9;
    animation: glow 3s ease-in-out infinite;
  }
  @keyframes glow {
    0%,
    100% {
      text-shadow: 0 0 18px rgba(34, 184, 196, 0.25);
    }
    50% {
      text-shadow: 0 0 26px rgba(34, 184, 196, 0.55);
    }
  }
  .msg {
    font-size: 0.875rem;
    color: #94a3b8;
  }
  @media (prefers-reduced-motion: reduce) {
    .name {
      animation: none;
    }
    .content {
      animation: none;
    }
  }
</style>
