<script lang="ts">
  // メニューページ共通の見出し（タイトル + 1 行説明）。各ページ上部に置き、そのページで何ができるかを示す。
  type Props = { title: string; description: string };
  const { title, description }: Props = $props();
</script>

<div>
  <h1 class="font-display text-lg font-semibold">{title}</h1>
  <p class="mt-0.5 text-xs leading-relaxed text-muted-foreground">{description}</p>
</div>
