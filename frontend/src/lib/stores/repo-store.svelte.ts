import type { Repository } from "$lib/api/schemas";

class RepoStore {
  connected = $state<Repository | null>(null);
  selectedBranch = $state<string>("main");

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
