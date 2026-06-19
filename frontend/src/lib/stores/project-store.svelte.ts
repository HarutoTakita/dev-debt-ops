import type { Project } from "$lib/api/schemas";
import { listProjects } from "$lib/api/client";

const RECENT_KEY = "rosetta:project:recent";
const RECENT_LIMIT = 10;

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
  /** org slug → 最近開いたプロジェクト id（新しい順） */
  private recentByOrg = $state<Record<string, string[]>>({});

  constructor() {
    if (typeof localStorage !== "undefined") {
      try {
        const raw = localStorage.getItem(RECENT_KEY);
        this.recentByOrg = raw ? (JSON.parse(raw) as Record<string, string[]>) : {};
      } catch {
        this.recentByOrg = {};
      }
    }
  }

  setCurrent(project: Project | null) {
    this.current = project;
  }

  /** org のプロジェクト一覧をロードしてスイッチャー用に保持する。 */
  async loadList(orgSlug: string): Promise<Project[]> {
    this.loading = true;
    try {
      this.list = await listProjects(orgSlug);
    } catch {
      this.list = [];
    } finally {
      this.loading = false;
    }
    return this.list;
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
