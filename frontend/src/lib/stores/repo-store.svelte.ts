import type { Branch, Repository, Tree } from "$lib/api/schemas";

class RepoStore {
  connected = $state<Repository | null>(null);
  selectedBranch = $state<string>("main");
  // ファイルツリー / ブランチのセッションキャッシュ（owner/repo@branch 単位）。同一リポジトリへ再訪したとき
  // 即表示するための stale-while-revalidate 用。リアクティブ不要（読み出した値を tree/branches に入れる）。
  treeCache = new Map<string, Tree>();
  branchCache = new Map<string, Branch[]>();

  connect(repo: Repository) {
    this.connected = repo;
    this.selectedBranch = repo.default_branch;
  }

  disconnect() {
    this.connected = null;
    this.selectedBranch = "main";
  }
}

export const repo = new RepoStore();
