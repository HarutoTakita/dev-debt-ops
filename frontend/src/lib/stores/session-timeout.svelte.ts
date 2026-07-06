// 無操作セッションタイムアウト（クライアント計測）。30 分無操作で強制ログアウト、残り 5 分で警告モーダル。
//
// 方式:
// - 経過は「最終操作時刻との時刻差分」で判定する（背景タブで setInterval が間引かれても、復帰時に正しく判定）。
// - 操作検知はスロットルし、他タブへ最終操作時刻を BroadcastChannel + localStorage で共有（マルチタブ同期）。
//   → 別タブで操作していれば全タブのタイマーがリセットされ、見ていないタブのタイマーで落ちない。
// - デモユーザーは対象外（呼び出し側 = [org] レイアウトで start しない）。
// - 強制ログアウトは auth.logout()（サーバ失効 + Cookie 削除 + /login 遷移）を呼ぶ。

import { auth } from "./auth.svelte";

const TIMEOUT_MS = 30 * 60 * 1000; // 無操作で強制ログアウトするまで（30 分）
const WARN_MS = 5 * 60 * 1000; // 残りこの時間で警告モーダルを出す（5 分）
const WARN_AT_MS = TIMEOUT_MS - WARN_MS; // 無操作 25 分で警告
const TICK_MS = 1000; // 判定間隔（カウントダウン表示のため 1 秒）
const BROADCAST_THROTTLE_MS = 3000; // 他タブへの共有頻度の上限
const CHANNEL_NAME = "ddo-session-activity";
const STORAGE_KEY = "ddo:last-activity"; // BroadcastChannel 非対応時のフォールバック（storage イベント）
const ACTIVITY_EVENTS = ["mousemove", "mousedown", "keydown", "scroll", "touchstart", "click"] as const;

class SessionTimeout {
  // 警告モーダルの表示状態と残り時間（カウントダウン表示用）。
  showWarning = $state(false);
  remainingMs = $state(WARN_MS);

  #active = false;
  /** 監視中か。モーダルの「閉じる＝延長」判定に使う（stop() 由来のプログラム的クローズで延長しないため）。 */
  get active() {
    return this.#active;
  }
  #last = 0; // 最終操作時刻（自タブ + 他タブ由来の最大値）
  #lastBroadcast = 0;
  #interval: ReturnType<typeof setInterval> | undefined;
  #channel: BroadcastChannel | null = null;
  #onActivity = () => this.#recordActivity(false);
  #onStorage = (e: StorageEvent) => {
    if (e.key === STORAGE_KEY && e.newValue) this.#applyRemote(Number(e.newValue));
  };

  /** 監視を開始（認証済み・非デモのときに呼ぶ）。冪等。 */
  start() {
    if (this.#active || typeof window === "undefined") return;
    this.#active = true;
    this.#last = Date.now();
    this.#lastBroadcast = 0;
    for (const ev of ACTIVITY_EVENTS) window.addEventListener(ev, this.#onActivity, { passive: true });
    window.addEventListener("storage", this.#onStorage);
    try {
      this.#channel = new BroadcastChannel(CHANNEL_NAME);
      this.#channel.onmessage = (e) => this.#applyRemote(Number(e.data));
    } catch {
      this.#channel = null; // 非対応環境は storage イベントにフォールバック
    }
    this.#interval = setInterval(() => this.#tick(), TICK_MS);
  }

  /** 監視を停止（ログアウト・デモ・アンマウント時）。冪等。 */
  stop() {
    if (!this.#active) return;
    this.#active = false;
    for (const ev of ACTIVITY_EVENTS) window.removeEventListener(ev, this.#onActivity);
    window.removeEventListener("storage", this.#onStorage);
    if (this.#interval) clearInterval(this.#interval);
    this.#interval = undefined;
    this.#channel?.close();
    this.#channel = null;
    this.showWarning = false;
  }

  /** 「操作を続ける」= 明示操作としてタイマーをリセットし、警告を閉じる。 */
  extend() {
    this.#recordActivity(true);
  }

  #recordActivity(force: boolean) {
    const now = Date.now();
    this.#last = now;
    // 警告中・force のときは必ず反映。通常操作はスロットルして broadcast 頻度を抑える。
    if (!force && !this.showWarning && now - this.#lastBroadcast < BROADCAST_THROTTLE_MS) return;
    this.#lastBroadcast = now;
    if (this.showWarning) this.showWarning = false;
    try {
      this.#channel?.postMessage(now);
    } catch {
      /* ignore */
    }
    try {
      localStorage.setItem(STORAGE_KEY, String(now));
    } catch {
      /* ignore（プライベートモード等） */
    }
  }

  // 他タブの操作を反映（より新しい最終操作時刻を採用）。
  #applyRemote(ts: number) {
    if (Number.isFinite(ts) && ts > this.#last) {
      this.#last = ts;
      if (this.showWarning) this.showWarning = false;
    }
  }

  #tick() {
    const idle = Date.now() - this.#last;
    if (idle >= TIMEOUT_MS) {
      this.stop();
      void auth.logout();
      return;
    }
    if (idle >= WARN_AT_MS) {
      this.remainingMs = Math.max(0, TIMEOUT_MS - idle);
      this.showWarning = true;
    } else if (this.showWarning) {
      this.showWarning = false;
    }
  }
}

export const sessionTimeout = new SessionTimeout();
