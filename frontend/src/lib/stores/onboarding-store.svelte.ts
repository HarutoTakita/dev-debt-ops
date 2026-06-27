// オンボーディングガイド（プロダクトツアー）の状態（issue 066）。
// 初回プロジェクト作成時に自動開始し、完了/スキップで org ごとに完了フラグを localStorage 永続。
// 以降は自動表示せず、サイドバーの ? → ヘルプページからいつでも再生できる。
// 永続の前例: project-store / sidebar-store / recent-searches（同じ rosetta:* キー規約）。

import type { TourStep } from "$lib/components/onboarding/tour-steps";

const KEY = "rosetta:onboarding";

type Persisted = { completedByOrg: Record<string, boolean> };

class OnboardingStore {
  // ツアー実行状態（リアクティブ）。
  active = $state(false);
  stepIndex = $state(0);
  // 現在実行中のステップ列（メイン手順 or ページ別ガイド）。
  steps = $state<TourStep[]>([]);
  // ページ別ガイドを表示中か（true のとき「全体ガイドに戻る」を出す）。
  inDetail = $state(false);
  // 「詳細を確認する」で抜ける前のメイン手順の位置（全体ガイドへ戻すため）。
  #mainReturn: { steps: TourStep[]; stepIndex: number } | null = null;

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

  /** 指定したステップ列でツアーを開始（全体ガイド）。詳細からの復帰位置はクリアする。 */
  start(steps: TourStep[]) {
    this.#mainReturn = null;
    this.inDetail = false;
    this.steps = steps;
    this.stepIndex = 0;
    this.active = true;
  }

  /** 「詳細を確認する」: 現在のメイン位置を覚えてページ別ガイドへ切り替える。 */
  startDetail(steps: TourStep[]) {
    this.#mainReturn = { steps: this.steps, stepIndex: this.stepIndex };
    this.inDetail = true;
    this.steps = steps;
    this.stepIndex = 0;
    this.active = true;
  }

  /** 詳細ガイドから全体ガイドの元の位置へ戻る。 */
  backToMain() {
    if (this.#mainReturn) {
      this.steps = this.#mainReturn.steps;
      this.stepIndex = this.#mainReturn.stepIndex;
      this.#mainReturn = null;
    }
    this.inDetail = false;
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
    this.#mainReturn = null;
    this.inDetail = false;
    if (orgSlug) {
      this.#completed = { ...this.#completed, [orgSlug]: true };
      this.#persist();
    }
  }
}

export const onboarding = new OnboardingStore();
export { OnboardingStore };
