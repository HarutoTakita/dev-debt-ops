# 主要画面の下部見切れ（メインコンテンツがスクロールしない）を修正する

## 概要
観測台（Overview）や負債マトリクス（Matrix）など、コンテンツが縦に長い画面で**下部が見切れてスクロールできない**。アプリシェルのメインコンテンツ領域に `overflow-hidden` が当たっており、ビューポートを超えた分が単に切り取られてスクロールバーも出ない状態。

## 背景・目的
ダッシュボードや一覧は内容が縦に伸びるため、メイン領域は縦スクロール可能であるべき。現状は折り返し以下の情報（優先度リスト、トレンド、活動量など）にアクセスできず、機能が「壊れている」ように見える。1 箇所の CSS 是正で全機能画面が直る。

## タスク
- [ ] `frontend/src/routes/[org]/+layout.svelte` のメイン領域 `<main class="min-w-0 flex-1 overflow-hidden">` を、縦スクロール可能に変更する（`overflow-hidden` → `overflow-y-auto`、必要に応じて `min-h-0` の付与を確認）。
- [ ] 外側の高さ配分（`flex h-screen flex-col` / 内側 `flex min-h-0 flex-1`）が崩れていないか確認し、メインだけがスクロールしトップバー/サイドバーは固定される構成にする。
- [ ] 各機能ページ側（`overview` / `matrix` / `galaxy` / `quizzes` / `learning` / `repos` の `+page.svelte`）に独自の `overflow-hidden` や固定高さが無いか確認し、二重クリップを除去する。
- [ ] モバイル幅（Sheet サイドバー）でも下部までスクロールできることを確認する。
- [ ] スクロール位置のリセット（ルート遷移時に先頭へ）を必要なら整える。

## 完了条件
- Overview / Matrix を含む全機能画面で、ビューポートを超える内容が**縦スクロールで最後まで閲覧できる**。
- トップバーとサイドバーは固定され、メイン領域のみがスクロールする。
- デスクトップ／モバイル幅の双方で見切れが発生しない。

## 技術詳細
- 主因: `frontend/src/routes/[org]/+layout.svelte:33` `<main class="min-w-0 flex-1 overflow-hidden">` — `overflow-hidden` が縦溢れをクリップし、スクロールが発生しない。
- 周辺: 同ファイル `:11-14` の `flex h-screen flex-col` / `flex min-h-0 flex-1`（高さ配分自体は妥当）。
- 影響ルート: `frontend/src/routes/[org]/[project]/+page.svelte`（観測台）, `.../matrix/+page.svelte`（負債マトリクス）ほか縦長の全画面。
- 修正方針例: `<main class="min-w-0 flex-1 overflow-y-auto">`（必要なら `overscroll-contain` を併用）。

## 参考
- 関連: [023 ローディング/エラー/空状態](./023-frontend-loading-error-empty-states.md)、[024 アクセシビリティとレスポンシブ](./024-frontend-accessibility-and-responsive.md)
- 想定ラベル: `bug`, `frontend`
