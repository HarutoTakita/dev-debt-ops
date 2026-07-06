# 無操作セッションタイムアウト（残り 5 分警告 → 30 分で強制ログアウト）

## 概要

一定時間（**30 分**）操作が無いユーザーを自動でログアウトさせ、離席中の端末に開きっぱなしのセッションが
残り続けるのを防ぐ。ログアウトの **5 分前（＝無操作 25 分）** にモーダルで警告し、そのまま無操作が続けば
30 分でサーバセッションを失効させてログイン画面へ戻す。マルチタブでも一貫した挙動にする。

## 背景 / 目的

- アクセストークンは 8 時間・リフレッシュは 30 日と長寿命で、サーバは**アイドル時間を追跡していない**。
  そのため離席してもセッションが長時間有効なままになる（共有端末・公共環境でのリスク）。
- 「無操作でのタイムアウト」は UX ポリシーであり、**クライアント側で計測**し、時間切れ時に既存のログアウト
  API を呼んでサーバセッションも確実に失効させる方針とする（`/logout` は refresh 行の失効 + `token_epoch`
  更新 + Cookie 削除を行うため、強制ログアウトは実効的）。

## 要件（確定仕様）

- 無操作 **30 分**で強制ログアウト → ログイン画面（`/login`）へ遷移。
- 残り **5 分**（無操作 25 分）でモーダル警告を表示し、**カウントダウン**を出す。
  - 「操作を続ける」/ 画面操作 / Esc・外側クリック → タイマーをリセットして警告を閉じる。
  - 「今すぐログアウト」ボタンも用意。
- **マルチタブ同期**：あるタブで操作していれば全タブのタイマーがリセットされ、閲覧していないタブの
  タイマーでログアウトされない。全タブが無操作のときだけタイムアウトする。
- **デモユーザーは対象外**（ゲストデモ体験を妨げない）。
- 30 分 / 5 分は**固定値**。
- **サーバ側のアイドル強制は行わない**（クライアント計測 + ログアウト API で十分）。
- 背景タブで `setInterval` が間引かれても正しく判定できること（**最終操作時刻との差分**で判定）。

## 対応（実装）

すべてフロントエンド。バックエンドは既存のログアウト API を利用し、**変更なし**。

- `frontend/src/lib/stores/session-timeout.svelte.ts`（新規）
  - 最終操作時刻を保持し、`Date.now()` との**差分**で判定（背景タブでも正確）。
  - 操作イベント（`mousemove`/`mousedown`/`keydown`/`scroll`/`touchstart`/`click`）を購読し、スロットルして
    最終操作時刻を更新。
  - マルチタブ同期は **`BroadcastChannel`** ＋ **`localStorage`（storage イベント）フォールバック**で最終操作
    時刻を共有。より新しい時刻を全タブで採用。
  - 1 秒間隔のチェックで、無操作 25 分 →`showWarning=true`＋残り時間更新、30 分 →`stop()` + `auth.logout()`。
  - `start()` / `stop()` は冪等。停止由来のクローズを「延長」と誤認しないよう `active` ゲッターで区別。
- `frontend/src/lib/components/shell/session-timeout-dialog.svelte`（新規）
  - 警告モーダル（残り時間 `m:ss` カウントダウン、「操作を続ける」/「ログアウト」）。
  - `open` は `sessionTimeout.showWarning` に従い、Esc・外側クリックでの閉じは延長扱い（ただし監視停止中は無視）。
- `frontend/src/routes/+layout.svelte`（変更）
  - ルートレイアウトに `SessionTimeoutDialog` を設置し、`auth.isAuthenticated && !auth.isDemo` のときだけ
    `sessionTimeout.start()`。未認証（`/login` 等）・デモは対象外。全認証ページ（`/[org]/*`・`/account`・
    `/admin`）を一括カバー。
- `frontend/src/lib/stores/auth.svelte.ts`（変更）
  - ログアウト処理を `auth.logout()` に共通化（API 呼び出し → `clear()` → `/login`）。API 失敗でもローカルは
    必ずクリアして遷移。
- `frontend/src/lib/components/shell/user-menu.svelte`（変更）
  - ユーザーメニューのログアウトを共通 `auth.logout()` に変更。
- `frontend/messages/{ja,en}.json`（変更）
  - `session_timeout_title` / `session_timeout_desc`（`{time}` パラメータ）/ `session_timeout_continue`
    / `session_timeout_logout` を追加。

## 影響範囲

- フロントエンドのみ。**バックエンド・DB スキーマの変更なし**、マイグレーション不要。
- 既存のログアウト導線（ユーザーメニュー）は共通化のみで挙動は同等。
- ルートレイアウトに常時マウントされるが、未認証・デモでは何も起動しない。

## 受け入れ条件

- 認証済み（非デモ）ユーザーが 25 分無操作でモーダル警告＋カウントダウンが表示される。
- 「操作を続ける」または任意の操作でタイマーがリセットされ、警告が消える。
- 30 分無操作でログイン画面へ強制遷移し、サーバ側セッションが失効している（Cookie 削除・`token_epoch` 更新）。
- 複数タブを開いた状態で片方を操作すると、全タブのタイマーがリセットされる。
- デモユーザーではタイムアウトが発生しない。
- `/login` などの未認証ページでは監視が動かない。

## 参照

- 認証: `backend/api/app/api/v1/auth_custom.py`（`/logout`）、`backend/api/app/core/security.py`、
  `backend/api/app/core/config.py`（`JWT_LIFETIME_SECONDS` / `REFRESH_TOKEN_LIFETIME_SECONDS`）
- フロント: `frontend/src/lib/api/client.ts`（`apiFetch` の 401→refresh→`/login`）
- コミット: `5c53f0f`（実装）
