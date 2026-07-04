<script lang="ts">
  import { untrack } from "svelte";
  import { project } from "$lib/stores/project-store.svelte";
  import { repo } from "$lib/stores/repo-store.svelte";
  import { analysisRun } from "$lib/stores/analysis-run-store.svelte";
  import type { LayoutData } from "./$types";

  let { data, children }: { data: LayoutData; children: import("svelte").Snippet } = $props();

  // 直近に設定したプロジェクト id。**プロジェクトが実際に切り替わった時だけ** 解析ランをリセットする。
  // （以前は effect クリーンアップで毎回 reset していたため、同一プロジェクト内のページ遷移でも
  //   実行中の解析ポーリングが中断され、完了しても自動反映されない不具合になっていた。）
  let currentProjectId: string | null = null;

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
      // 別プロジェクトへ切り替わったら、共有の解析ラン singleton をクリアして A のステージ/ディープリンクが
      // B に漏れないようにし、実行中ポーリングを中断する（issue-044）。同一プロジェクト内の遷移では消さない。
      if (currentProjectId !== null && currentProjectId !== p.id) {
        analysisRun.reset();
      }
      currentProjectId = p.id;
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
      });
    };
  });
</script>

{@render children()}
