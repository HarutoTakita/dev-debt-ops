import type { Project } from "$lib/api/schemas";
import { listProjects } from "$lib/api/client";

const RECENT_KEY = "rosetta:project:recent";
const RECENT_LIMIT = 10;
const GETTING_STARTED_KEY = "rosetta:getting-started:dismissed";

/**
 * 選択中プロジェクト・org のプロジェクト一覧・「最近開いた順」を管理する。
 *
 * frecency のサーバ側集計（GitLab の visitable.rb 相当）は MVP では持たず、
 * 直近性のみの軽量版を localStorage（org 別）に保持する。
 */
class ProjectStore {
  /** 現在のワークスペース（[org]/[project] レイアウトで解決してセット） */
  current = $state<Project | null>(null);
  /** スイッチャー用の org 内プロジェクト一覧 */
  list = $state<Project[]>([]);
  loading = $state(false);
  /** loadList が失敗 / タイムアウトしたか（確定空と区別する） */
  error = $state<string | null>(null);
  /** org slug → 最近開いたプロジェクト id（新しい順） */
  private recentByOrg = $state<Record<string, string[]>>({});
  /** "orgSlug/projectSlug" → getting-started を閉じたか */
  private gettingStartedDismissed = $state<Record<string, boolean>>({});

  constructor() {
    if (typeof localStorage !== "undefined") {
      try {
        const raw = localStorage.getItem(RECENT_KEY);
        this.recentByOrg = raw ? (JSON.parse(raw) as Record<string, string[]>) : {};
      } catch {
        this.recentByOrg = {};
      }
      try {
        const raw = localStorage.getItem(GETTING_STARTED_KEY);
        this.gettingStartedDismissed = raw ? (JSON.parse(raw) as Record<string, boolean>) : {};
      } catch {
        this.gettingStartedDismissed = {};
      }
    }
  }

  /** getting-started（はじめに）を閉じたか（プロジェクト別）。 */
  isGettingStartedDismissed(key: string): boolean {
    return this.gettingStartedDismissed[key] === true;
  }

  /** getting-started を閉じて永続化する。 */
  dismissGettingStarted(key: string) {
    this.gettingStartedDismissed = { ...this.gettingStartedDismissed, [key]: true };
    if (typeof localStorage !== "undefined") {
      localStorage.setItem(GETTING_STARTED_KEY, JSON.stringify(this.gettingStartedDismissed));
    }
  }

  setCurrent(project: Project | null) {
    this.current = project;
  }

  /** org のプロジェクト一覧をロードしてスイッチャー用に保持する。失敗/タイムアウトは error に記録する。 */
  async loadList(orgSlug: string): Promise<Project[]> {
    this.loading = true;
    this.error = null;
    try {
      this.list = await this.#withTimeout(listProjects(orgSlug), 10_000);
    } catch (e) {
      this.list = [];
      this.error = e instanceof Error ? e.message : "load failed";
    } finally {
      this.loading = false;
    }
    return this.list;
  }

  /** 一定時間で打ち切るタイムアウト付きラッパ（失敗分岐へ合流させる）。 */
  #withTimeout<T>(p: Promise<T>, ms: number): Promise<T> {
    return new Promise<T>((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("timeout")), ms);
      p.then(
        (v) => {
          clearTimeout(timer);
          resolve(v);
        },
        (e) => {
          clearTimeout(timer);
          reject(e);
        },
      );
    });
  }

  /** 「最近開いた順」を更新して永続化する。 */
  touch(orgSlug: string, projectId: string) {
    const prev = (this.recentByOrg[orgSlug] ?? []).filter((id) => id !== projectId);
    this.recentByOrg = { ...this.recentByOrg, [orgSlug]: [projectId, ...prev].slice(0, RECENT_LIMIT) };
    if (typeof localStorage !== "undefined") {
      localStorage.setItem(RECENT_KEY, JSON.stringify(this.recentByOrg));
    }
  }

  /** org の最近開いたプロジェクトを、現在の一覧から新しい順に解決して返す。 */
  recentProjects(orgSlug: string): Project[] {
    const ids = this.recentByOrg[orgSlug] ?? [];
    const byId = new Map(this.list.map((p) => [p.id, p]));
    return ids.map((id) => byId.get(id)).filter((p): p is Project => p !== undefined);
  }
}

export const project = new ProjectStore();
