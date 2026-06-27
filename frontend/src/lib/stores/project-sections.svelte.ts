const KEY = "rosetta:project-sections";

/** セクション見出しのアイコン色（Tailwind の完全クラス名で持つ — JIT 生成のため動的合成しない）。 */
export const SECTION_ICON_COLORS = [
  "text-debt-knowledge",
  "text-debt-code",
  "text-emerald-500",
  "text-sky-500",
  "text-violet-500",
  "text-rose-500",
  "text-amber-500",
  "text-teal-500",
];

/** ユーザー定義セクション（Slack のサイドバーセクション相当）。 */
export interface ProjectSection {
  id: string;
  name: string;
  /** SECTION_ICON_COLORS のインデックス（カラフルなアイコン色）。 */
  color: number;
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

  /** 新規セクションを作成して id を返す。色はパレットを作成順で巡回して割り当てる。 */
  createSection(org: string, name: string): string {
    const id = crypto.randomUUID();
    const v = this.#view(org);
    const color = v.sections.length % SECTION_ICON_COLORS.length;
    this.#commit(org, { ...v, sections: [...v.sections, { id, name: name.trim() || "新しいセクション", color }] });
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

  /**
   * ドラッグ&ドロップ用: プロジェクトを表示グループ（スター付き / セクション / 既定）へ移動する。
   * ドロップ先に必ず現れるよう、スター付き以外へ移すときは star を外す（1 グループ表示の原則）。
   */
  moveToGroup(org: string, projectId: string, groupKey: string) {
    const v = this.#view(org);
    let starred = v.starred;
    const assignments = { ...v.assignments };
    if (groupKey === STARRED_KEY) {
      if (!starred.includes(projectId)) starred = [...starred, projectId];
    } else {
      starred = starred.filter((id) => id !== projectId);
      if (groupKey === DEFAULT_KEY) delete assignments[projectId];
      else assignments[projectId] = groupKey;
    }
    this.#commit(org, { ...v, starred, assignments });
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
