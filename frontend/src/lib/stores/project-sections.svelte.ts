const KEY = "rosetta:project-sections";

/** ユーザー定義セクション（Slack のサイドバーセクション相当）。 */
export interface ProjectSection {
  id: string;
  name: string;
}

interface OrgView {
  /** スター付きプロジェクト id（表示は先頭の「スター付き」グループへ集約）。 */
  starred: string[];
  /** ユーザー定義セクション（表示順）。 */
  sections: ProjectSection[];
  /** projectId → sectionId（未割り当て = 既定の「プロジェクト」グループ）。 */
  assignments: Record<string, string>;
  /** 折りたたみ中のグループ key（セクション id、または "__starred__" / "__default__"）。 */
  collapsed: string[];
}

type State = Record<string, OrgView>;

export const STARRED_KEY = "__starred__";
export const DEFAULT_KEY = "__default__";

function emptyView(): OrgView {
  return { starred: [], sections: [], assignments: {}, collapsed: [] };
}

function load(): State {
  if (typeof localStorage === "undefined") return {};
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as State) : {};
  } catch {
    return {};
  }
}

/**
 * プロジェクトの「スター付き」と「ユーザー定義セクション」を org 別に保持する（Slack 風）。
 *
 * バックエンドは持たず localStorage に永続化する（`project-store` の recent/最近開いた順と同じ方針）。
 * 表示上、各プロジェクトは「スター付き → 割り当てセクション → 既定」のいずれか 1 グループにのみ現れる。
 */
class ProjectSectionsStore {
  #state = $state<State>(load());

  #view(org: string): OrgView {
    return this.#state[org] ?? emptyView();
  }

  #commit(org: string, view: OrgView) {
    this.#state = { ...this.#state, [org]: view };
    if (typeof localStorage !== "undefined") {
      localStorage.setItem(KEY, JSON.stringify(this.#state));
    }
  }

  // --- スター ---
  isStarred(org: string, projectId: string): boolean {
    return this.#view(org).starred.includes(projectId);
  }

  toggleStar(org: string, projectId: string) {
    const v = this.#view(org);
    const starred = v.starred.includes(projectId)
      ? v.starred.filter((id) => id !== projectId)
      : [...v.starred, projectId];
    this.#commit(org, { ...v, starred });
  }

  // --- セクション ---
  sections(org: string): ProjectSection[] {
    return this.#view(org).sections;
  }

  /** projectId が属するセクション id（未割り当ては null）。 */
  sectionOf(org: string, projectId: string): string | null {
    return this.#view(org).assignments[projectId] ?? null;
  }

  /** 新規セクションを作成して id を返す。 */
  createSection(org: string, name: string): string {
    const id = crypto.randomUUID();
    const v = this.#view(org);
    this.#commit(org, { ...v, sections: [...v.sections, { id, name: name.trim() || "新しいセクション" }] });
    return id;
  }

  renameSection(org: string, sectionId: string, name: string) {
    const v = this.#view(org);
    const sections = v.sections.map((s) => (s.id === sectionId ? { ...s, name: name.trim() || s.name } : s));
    this.#commit(org, { ...v, sections });
  }

  /** セクションを削除し、所属プロジェクトを既定グループへ戻す。 */
  deleteSection(org: string, sectionId: string) {
    const v = this.#view(org);
    const sections = v.sections.filter((s) => s.id !== sectionId);
    const assignments: Record<string, string> = {};
    for (const [pid, sid] of Object.entries(v.assignments)) {
      if (sid !== sectionId) assignments[pid] = sid;
    }
    const collapsed = v.collapsed.filter((k) => k !== sectionId);
    this.#commit(org, { ...v, sections, assignments, collapsed });
  }

  /** プロジェクトをセクションへ割り当てる（sectionId=null で既定グループへ戻す）。 */
  assign(org: string, projectId: string, sectionId: string | null) {
    const v = this.#view(org);
    const assignments = { ...v.assignments };
    if (sectionId === null) delete assignments[projectId];
    else assignments[projectId] = sectionId;
    this.#commit(org, { ...v, assignments });
  }

  // --- グループ折りたたみ ---
  isCollapsed(org: string, key: string): boolean {
    return this.#view(org).collapsed.includes(key);
  }

  toggleCollapsed(org: string, key: string) {
    const v = this.#view(org);
    const collapsed = v.collapsed.includes(key) ? v.collapsed.filter((k) => k !== key) : [...v.collapsed, key];
    this.#commit(org, { ...v, collapsed });
  }
}

export const projectSections = new ProjectSectionsStore();
