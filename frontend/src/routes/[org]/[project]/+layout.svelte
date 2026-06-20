<script lang="ts">
  import { untrack } from "svelte";
  import { project } from "$lib/stores/project-store.svelte";
  import { repo } from "$lib/stores/repo-store.svelte";
  import { analysisRun } from "$lib/stores/analysis-run-store.svelte";
  import type { LayoutData } from "./$types";

  let { data, children }: { data: LayoutData; children: import("svelte").Snippet } = $props();

  // 解決したプロジェクトを現在ワークスペースに設定し、その束縛リポジトリを
  // 既存の repo-store に橋渡しする。これにより repo.connected を読む既存機能
  // （Overview / Repos など）が、選択中プロジェクトのリポジトリで動作する。
  //
  // 依存は data.project / data.orgSlug（= ナビゲーション）のみにする。ストア更新は
  // untrack で包む — touch() は recentByOrg を read+write するため、追跡されると
  // 自分の書き込みで再実行され続け無限ループ（effect_update_depth_exceeded）になる。
  $effect(() => {
    const p = data.project;
    const orgSlug = data.orgSlug;
    untrack(() => {
      project.setCurrent(p);
      project.touch(orgSlug, p.id);
      repo.connect({
        owner: p.repo_owner,
        name: p.repo_name,
        full_name: p.repo_full_name,
        default_branch: p.default_branch,
        private: p.repo_private,
        updated_at: p.created_at,
      });
    });
    return () => {
      untrack(() => {
        project.setCurrent(null);
        repo.disconnect();
        // Clear the shared analysis-run singleton so project A's stages / deep-links don't leak
        // into project B and so in-flight polls are cancelled on project switch (issue-044).
        analysisRun.reset();
      });
    };
  });
</script>

{@render children()}
