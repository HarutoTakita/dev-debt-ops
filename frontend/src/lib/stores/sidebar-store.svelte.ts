const COLLAPSED_KEY = "rosetta:sidebar:collapsed";

class SidebarStore {
  /** トグル: アイコンのみ表示 */
  collapsed = $state(false);
  /** 狭幅（モバイル）でのサイドバーオーバーレイ開閉 */
  mobileOpen = $state(false);

  constructor() {
    if (typeof localStorage !== "undefined") {
      this.collapsed = localStorage.getItem(COLLAPSED_KEY) === "1";
    }
  }

  toggle() {
    this.collapsed = !this.collapsed;
    this.persistCollapsed();
  }

  private persistCollapsed() {
    if (typeof localStorage !== "undefined") {
      localStorage.setItem(COLLAPSED_KEY, this.collapsed ? "1" : "0");
    }
  }
}

export const sidebar = new SidebarStore();
