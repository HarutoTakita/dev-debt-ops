import type { Repository } from "$lib/api/schemas";

class RepoStore {
  connected = $state<Repository | null>(null);
  selectedBranch = $state<string>("main");
  // 解析ライフサイクル（偽データを本物に見せない）。接続直後は scanning、完了で done。
  scanState = $state<"idle" | "scanning" | "done">("idle");
  // 直近スキャン済みリポジトリ。disconnect/再 connect（サブページ間の再ナビゲーション）で
  // 同一 repo に戻ったときにスキャン演出を繰り返さないため（issue-044）。
  #scannedFullName: string | null = null;

  connect(repo: Repository) {
    this.connected = repo;
    this.selectedBranch = repo.default_branch;
    // 初回接続のみ scanning 演出を出す。既にスキャン済みの同一 repo は done のまま。
    this.scanState = this.#scannedFullName === repo.full_name ? "done" : "scanning";
  }

  finishScan() {
    this.scanState = "done";
    this.#scannedFullName = this.connected?.full_name ?? null;
  }

  disconnect() {
    this.connected = null;
    this.selectedBranch = "main";
    this.scanState = "idle";
    // #scannedFullName は意図的に保持 — 同一 repo へ戻ったときの再スキャンを防ぐ。
  }
}

export const repo = new RepoStore();
