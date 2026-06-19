import type { Repository } from "$lib/api/schemas";

class RepoStore {
  connected = $state<Repository | null>(null);
  selectedBranch = $state<string>("main");
  // 解析ライフサイクル（偽データを本物に見せない）。接続直後は scanning、完了で done。
  scanState = $state<"idle" | "scanning" | "done">("idle");

  connect(repo: Repository) {
    this.connected = repo;
    this.selectedBranch = repo.default_branch;
    this.scanState = "scanning";
  }

  finishScan() {
    this.scanState = "done";
  }

  disconnect() {
    this.connected = null;
    this.selectedBranch = "main";
    this.scanState = "idle";
  }
}

export const repo = new RepoStore();
