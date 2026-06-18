const COLLAPSED_KEY = "rosetta:sidebar:collapsed";
const PINNED_KEY = "rosetta:sidebar:pinned";

class SidebarStore {
  /** トグル: アイコンのみ表示 */
  collapsed = $state(false);
  /** ピン留めされた項目 id */
  pinnedIds = $state<string[]>([]);
  /** 狭幅（モバイル）でのサイドバーオーバーレイ開閉 */
  mobileOpen = $state(false);

  constructor() {
    if (typeof localStorage !== "undefined") {
      this.collapsed = localStorage.getItem(COLLAPSED_KEY) === "1";
      try {
        const raw = localStorage.getItem(PINNED_KEY);
        this.pinnedIds = raw ? (JSON.parse(raw) as string[]) : [];
      } catch {
        this.pinnedIds = [];
      }
    }
  }

  toggle() {
    this.collapsed = !this.collapsed;
    this.persistCollapsed();
  }

  togglePin(id: string) {
    this.pinnedIds = this.pinnedIds.includes(id) ? this.pinnedIds.filter((p) => p !== id) : [...this.pinnedIds, id];
    if (typeof localStorage !== "undefined") {
      localStorage.setItem(PINNED_KEY, JSON.stringify(this.pinnedIds));
    }
  }

  isPinned(id: string): boolean {
    return this.pinnedIds.includes(id);
  }

  private persistCollapsed() {
    if (typeof localStorage !== "undefined") {
      localStorage.setItem(COLLAPSED_KEY, this.collapsed ? "1" : "0");
    }
  }
}

export const sidebar = new SidebarStore();
