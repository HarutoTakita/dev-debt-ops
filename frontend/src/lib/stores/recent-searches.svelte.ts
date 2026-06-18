import type { DebtFilter } from "$lib/api/client";

// GitLab recent_searches_service.js の写像。負債フィルタの直近条件を localStorage に保存する。
// キー: rosetta:recent-debt-searches:<orgSlug> / 最大 5 件。
const MAX = 5;

function hasAnyFilter(f: DebtFilter): boolean {
  return Boolean(f.kind?.length || f.severity?.length || f.agent?.length || f.status?.length);
}

class RecentSearchesStore {
  searches = $state<DebtFilter[]>([]);
  #key = "";

  load(orgSlug: string) {
    this.#key = `rosetta:recent-debt-searches:${orgSlug}`;
    if (typeof localStorage === "undefined") return;
    try {
      const raw = localStorage.getItem(this.#key);
      this.searches = raw ? (JSON.parse(raw) as DebtFilter[]) : [];
    } catch {
      this.searches = [];
    }
  }

  add(filter: DebtFilter) {
    if (!hasAnyFilter(filter)) return; // 空条件は履歴に残さない
    const key = JSON.stringify(filter);
    const deduped = this.searches.filter((s) => JSON.stringify(s) !== key);
    this.searches = [filter, ...deduped].slice(0, MAX);
    if (typeof localStorage !== "undefined") {
      localStorage.setItem(this.#key, JSON.stringify(this.searches));
    }
  }

  clear() {
    this.searches = [];
    if (typeof localStorage !== "undefined" && this.#key) localStorage.removeItem(this.#key);
  }
}

export const recentSearches = new RecentSearchesStore();
