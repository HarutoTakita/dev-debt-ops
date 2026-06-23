// オンボーディングガイド（プロダクトツアー）の状態（issue 066）。
// 初回プロジェクト作成時に自動開始し、完了/スキップで org ごとに完了フラグを localStorage 永続。
// 以降は自動表示せず、サイドバーの ? → ヘルプページからいつでも再生できる。
// 永続の前例: project-store / sidebar-store / recent-searches（同じ rosetta:* キー規約）。

const KEY = "rosetta:onboarding";

type Persisted = { completedByOrg: Record<string, boolean> };

class OnboardingStore {
  // ツアー実行状態（リアクティブ）。
  active = $state(false);
  stepIndex = $state(0);

  // org ごとの完了フラグ（永続）。自動開始判定にのみ使うため非リアクティブで十分。
  #completed: Record<string, boolean> = {};
  // 初回作成 → 遷移後シェルでの自動開始を伝えるワンショット（永続しない）。
  #pendingStartOrg: string | null = null;

  constructor() {
    if (typeof localStorage !== "undefined") {
      try {
        const raw = localStorage.getItem(KEY);
        const p = raw ? (JSON.parse(raw) as Persisted) : null;
        this.#completed = p?.completedByOrg ?? {};
      } catch {
        this.#completed = {};
      }
    }
  }

  #persist() {
    if (typeof localStorage !== "undefined") {
      localStorage.setItem(KEY, JSON.stringify({ completedByOrg: this.#completed } satisfies Persisted));
    }
  }

  isCompleted(orgSlug: string): boolean {
    return Boolean(this.#completed[orgSlug]);
  }

  /** 初回プロジェクト作成時に呼ぶ。遷移先のシェルで一度だけ自動開始させる。 */
  requestAutoStart(orgSlug: string) {
    this.#pendingStartOrg = orgSlug;
  }

  /** シェル mount 時に呼ぶ。pending かつ未完了なら true（消費は 1 回のみ）。 */
  consumeAutoStart(orgSlug: string): boolean {
    if (this.#pendingStartOrg !== orgSlug) return false;
    this.#pendingStartOrg = null;
    return !this.isCompleted(orgSlug);
  }

  /** 手動開始（ヘルプページから）。 */
  start() {
    this.stepIndex = 0;
    this.active = true;
  }

  next() {
    this.stepIndex += 1;
  }

  prev() {
    if (this.stepIndex > 0) this.stepIndex -= 1;
  }

  /** 完了/スキップ。完了フラグを保存して自動表示を止める。 */
  finish(orgSlug: string) {
    this.active = false;
    this.stepIndex = 0;
    if (orgSlug) {
      this.#completed = { ...this.#completed, [orgSlug]: true };
      this.#persist();
    }
  }
}

export const onboarding = new OnboardingStore();
export { OnboardingStore };
