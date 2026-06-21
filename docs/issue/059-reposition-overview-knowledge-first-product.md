# Overview/IA を理解負債中心に再構成し、コード負債を「優先順位信号」へ降格する（プロダクト面）

## 概要
058（ナラティブ）の決定を**プロダクト UI / API**に反映する。Overview のヒーローを「理解負債（KC・Galaxy・
クイズ/学習ループ）」中心に再構成し、これまで二軸マトリクスで**コード負債と同格だった軸を“優先順位づけの信号”
へ降格**する。コード負債検知（028）・マトリクス自体は**残す**が、主役ではなく「どの理解ギャップが今ヤバいか」を
指すレンズ/フィルタとして位置づける。

> 本 issue はフロント中心 + 軽い API 調整。コード負債検知パイプラインは変更しない。

## 背景・目的

### 現状（コード負債と理解負債が同格）
- Overview の中心は二軸散布図（`frontend/src/lib/components/overview/debt-matrix.svelte`）で、X=コード負債 /
  Y=理解度（KC）が**対等**。優先度 `derive_priority(code, knowledge_coverage)`（`backend/api/app/services/debt_query.py`）も
  両軸対称に P0–P3 を出す。
- ナビ（`frontend/src/lib/config/nav.ts`）は `understand`（overview/galaxy/matrix）/ `knowledge`（quizzes/learning）/
  `reference` / `system`。理解負債の物語（測る→返済）が主役として前面化されていない。

### 目的
1. Overview のヒーローを「**このプロジェクト/機能をどれだけ理解しているか（KC）と、その返済導線**」にする。
2. コード負債を**第二の信号**に降格：マトリクスは残すが「危険なコード × 低理解 = 緊急の学習対象」という
   **理解負債の優先順位づけレンズ**として提示する（“技術負債を直せ”を主役にしない）。
3. ナビ/IA を理解負債の物語（診断＝Galaxy → 実測＝クイズ → 返済＝学習）に沿って整理する。

### 前提・連動
- **058** `docs/issue/058-reposition-knowledge-debt-first-narrative.md`（ポジショニング/コピーの決定元）。
- **052〜056**（機能単位の理解負債 / 粒度切替）。本 issue の Overview 再構成は 056 の粒度切替と統合する。
- **048/049/051**（Galaxy KC、オートリフレッシュ、ナビ IA 再編）の既存成果を流用。

## 設計方針

### Overview のヒーロー再構成
- トップに「**理解度サマリ**」：プロジェクト/機能の KC（org_kc / 機能別 KC）、未受験ベースライン、返済の進捗
  （学習完了・クイズ合格で上がった KC のトレンド）。Galaxy への導線を前面に。
- 二軸マトリクスは**残すが位置づけを変更**：見出しを「学習を優先すべき領域」等にし、**Y（理解度）を主軸**、
  **X（コード負債）を“緊急度の重み”**として読ませる。P0（危険×低理解）は「最優先で理解を埋めるべき領域」と表現。
- コード負債単体のレジストリ/ドリルダウンは**残すが副次導線**に降格（ナビ上位から外す or `reference` 寄りに）。

### 優先順位ロジックの再解釈（コード=信号）
- `derive_priority` は維持しつつ、**ラベルの意味を理解負債中心に再定義**（実装は据え置きでも UI 表現を変える）。
  必要なら「学習優先度」を `knowledge_coverage` 主・`code_debt_score` を重み係数とする派生スコアを API に追加検討
  （二軸対称の P0–P3 とは別に、`learning_priority` を 055 の機能集計に乗せる案）。
- コード負債は「**hotspot 信号**」として、低理解領域の緊急度を上げる入力に使う（危険なコードを誰も分かっていない＝放置リスク大）。

### ナビ / IA
- `understand`（Galaxy/Overview）と `knowledge`（quizzes/learning）を「**理解負債を測る → 返済する**」の一本の物語に整理（051 の延長）。
- コード負債（マトリクスのコード軸 / 負債レジストリ）はメインの物語から外し、補助タブ/フィルタへ。

## タスク

### frontend（`frontend/src/`）
- [ ] `overview` を再構成：理解度サマリ + Galaxy 導線をヒーロー化。マトリクスを「学習優先領域」レンズとして再配置（056 の粒度切替と統合）。
- [ ] `debt-matrix.svelte` の見出し/凡例/ツールチップを理解負債中心の表現に（Y=理解度を主役、X=コード負債を緊急度重みとして説明）。
- [ ] コード負債レジストリ/ドリルダウンを副次導線へ降格（`nav.ts` の位置調整、`reference` 寄せ等）。
- [ ] i18n（ja/en）コピーを 058 の決定に合わせて更新（マトリクス/Overview/ナビ）。
- [ ] 空状態・オンボーディングを「まず理解度を測ろう（ベースラインクイズ）」の導線に。

### api（`backend/api/app/`）— 軽量
- [ ] （任意）`learning_priority`（理解度主・コード負債を重みとする派生指標）を 055 の機能集計/Overview に追加検討。
      二軸 `derive_priority` は後方互換のため維持。
- [ ] コード負債は配信し続ける（削除しない）。レスポンス契約は据え置き（表現の変更はフロント主）。

### 整合
- [ ] 057（多粒度・コード負債拡張）の優先度低下を反映（コード負債の全粒度展開は後回し）。

## 完了条件
- Overview のヒーローが理解度（KC）と返済導線（Galaxy/クイズ/学習）中心になり、コード負債は「優先順位づけの信号」として副次的に提示される。
- 二軸マトリクスは残るが、理解負債を主軸・コード負債を緊急度の重みとして読める表現になっている。
- ナビ/IA が「理解負債を測る → 返済する」の物語に沿って整理される。
- コード負債検知（028）・配信 API・マトリクスを**削除していない**。
- フロント：`bun run check`（警告ゼロ）/ `bun run lint` / `bun run test:unit` が通る。
- `CHANGELOG.md`（日本語）に `Changed`（Overview/IA を理解負債中心に再構成、コード負債を信号へ降格）を追記。

## 対象外・保留
- **ナラティブ/README/ピッチ/仕様書の改稿** → 058。
- **コード負債検知ロジック・配信の削除**（行わない。信号として維持）。
- **機能単位の集計/粒度切替の実装本体** → 052〜056（本 issue はその上の見せ方の再構成）。

## 参考
- 既存実装：`frontend/src/lib/components/overview/debt-matrix.svelte`、`frontend/src/lib/config/nav.ts`、
  `frontend/src/lib/components/galaxy/*`、`backend/api/app/services/debt_query.py`（`build_overview` / `derive_priority`）。
- 連動 issue：[058 リポジション（ナラティブ）](./058-reposition-knowledge-debt-first-narrative.md)、
  [055 機能単位集計 API](./055-backend-feature-granularity-debt-aggregation-api.md)、
  [056 粒度切替 UI](./056-frontend-granularity-switch-and-feature-debt-view.md)、
  [051 ナビ/IA 再編](./051-nav-ia-restructure-agents-learning-quiz.md)、[057 多粒度・コード負債拡張](./057-multi-granularity-code-debt-rollout.md)（優先度低下）。
- 規約：`CLAUDE.md`（Svelte 5 runes・shadcn `ui/` 読取専用・Annotated DI 順序・snake_case 配信・i18n ja/en・CHANGELOG 日本語）。
