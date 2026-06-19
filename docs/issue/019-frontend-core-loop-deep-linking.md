# コアループ（診断 → 返済 → 検証）をディープリンクで配線する

## 概要

Overview / Matrix / Galaxy / Quizzes / Learning の 5 画面は個別には実装済みだが、
画面間の **遷移（ディープリンク）が未配線** で、操作可能に見えるノード（散布図の点・
星・優先リスト行・ギャップ概念）が実際にはどこにも飛ばない静的表示になっている。
本 issue は、これらの「見た目操作可能なノード」を実遷移につなぎ、
**診断（Overview/Matrix/Galaxy）→ 返済（Quizzes/Agents）→ 検証（Learning）** の
コアループを一つのストーリーとして辿れるようにする。**バックエンド不要**（フロントのみ）。

## 背景・目的

### 横断テーマ — ループは作られているがつながっていない

各画面は単体では成立しているが、リンクが張られていないため、デモで
「危険ファイルを見つけた → そのファイルの詳細を見る → クイズで返済する →
学習プランで検証する」という一連の流れを **クリックだけで辿れない**。
特に以下は UX 上の致命的なギャップである：

- `hover:scale-150` で **操作可能に見える** のに `onclick`/`href` を持たないノードが
  複数あり（散布図の点・Galaxy の星）、ユーザーの操作期待を裏切っている。
- クイズ結果やギャップ概念は表示されるだけで、次のアクション（学習・該当ファイル）へ
  導線がない。
- Matrix 側は URL クエリ（`cell`/`kind`/`severity`）からの **復元入口は既に実装済み**
  なのに、その入口へ飛ばす **発信側（Overview の各 affordance）が未配線**。

### 目的

1. 既に存在する遷移先（`/matrix?cell=...`・`/matrix/[debtId]`・`/quizzes`・
   `/learning?from=quiz`・`/galaxy`・`/agents`）へ、各画面の affordance を素直に配線する。
2. 「見た目操作可能」なノードに **実 onclick/href を与える** か、配線できないものは
   affordance（hover 拡大など）を外し、見た目と挙動を一致させる。
3. 既存の `resolve()`（`debt-list-row.svelte:15`）・URL クエリ復元（`matrix/+page.ts`）・
   ストア（`agent-store.svelte.ts`）を **再利用** し、新規データ層は最小限に留める。

### 前提・整合性（CLAUDE.md フロント規約）

- Svelte 5 runes のみ（`$state`/`$derived`/`$props`、`writable()`/`$:` 不使用）。
- shadcn-svelte@latest プリミティブは `ui/` *外* のラッパーで合成（`ui/` は読み取り専用）。
- ファイル/フォルダは kebab-case、文言は Paraglide 2.0（ja 主・en 従）。
- 遷移はすべて `resolve()`（`$app/paths`）でロケールプレフィックス整合を保つ。

## タスク

### rank 2b — quiz → learning ハンドオフを完結させる（重大 / S）

クイズ結果 CTA からの遷移時のみ Learning の本体（PlanProgress + ResourceList）を描画し、
サイドバー素遷移時は従来どおり Coming Soon を出す。`data.from` は **既に読込済み**で、
あとは `preview` の初期値に反映するだけ（実質 1 行修正）。

- [ ] `frontend/src/routes/[org]/[project]/learning/+page.svelte:9` の
      `let preview = $state(false)` を `let preview = $state(data.from === "quiz")` に変更し、
      quiz 経由時は本体（`PlanProgress`+`ResourceList`、現 31-42 の `{:else}` ブロック）を、
      素遷移時のみ Coming Soon（現 16-30）を出すようにする。
- [ ] `data.from`（`+page.ts:12` で `url.searchParams.get("from")` として読込済み）は
      現状 `:35` の sub-label 表示にしか使われていないことを確認し、分岐ソースに昇格する。
- [ ] クイズ結果 CTA（`constructive-result.svelte:44` の `<Button href={learningHref}>`）が
      `?from=quiz` を含む `learningHref` を渡していることを確認（呼び出し側 result ページ）。

> 補足: `PlanProgress` / `ResourceList` / `gap_concepts` 表示はすでに配線済み。
> 本タスクは「いつ本体を見せるか」のスイッチのみ。**バックエンド不要**。

### rank 4 — Overview → Matrix ディープリンク（重大 / S）

Matrix 側の **URL からの復元は実装済み**（`matrix/+page.ts:9-32` が `kind`/`severity`/`agent`/
`status` を `initialFilter` に、`cell` を読込；`matrix/+page.svelte:18` が `data.initialFilter`
で `filter` を seed）。未配線なのは Overview 側の **発信 affordance**。

- [ ] `priority-list.svelte:30-34` の各行（現状 `<li>` + `<span>`、リンクなし）を遷移可能にする。
      `FileDebt` は `path` を持つが debt id を持たないため（`priority-list.svelte:2`）、
      行は `/matrix?cell=danger`（または `?severity=critical`）へ飛ばす。
      `matrix/+page.ts` がこれらクエリを解釈する。
- [ ] `debt-matrix.svelte:57-71` の散布図の点（現状 `onmouseenter`/`onfocus` のみの `<button>`）に
      `onclick`/`href` を与え、危険点は `/matrix?cell=danger`、それ以外は `/matrix` へ遷移させる
      （個別 debt 詳細は `FileDebt` に id が無いため `path` ベースでは飛べない — クエリ遷移に留める）。
- [ ] `debt-matrix.svelte:36` の危険象限セル（現状 `bg-destructive/15` の素の `<div>`）を
      `/matrix?cell=danger` へのリンク/クリックにする。
- [ ] `quadrant-legend.svelte:21-28` の danger 行（現状 `<li>`、`items[]` に href なし）に
      該当象限への遷移を付ける（`items` に `cell` を持たせ `/matrix?cell=<cell>` を生成）。
- [ ] 遷移生成は `debt-list-row.svelte:15` の `resolve()` パターンを再利用する。

> 補足: priority-list / debt-matrix の点は **debt id を持たない**ため、
> `/matrix/[debtId]` 直リンクは不可。本 issue ではクエリ遷移（`?cell`/`?severity`）に統一する。
> **バックエンド不要**。

### rank 8 — Galaxy → Quizzes 接続（重大 / M）

Galaxy の低 KC ノード（`black_hole`/`dim_star`）から「クイズで返済」へ導線を引く。

- [ ] `mastery-list.svelte:24-41` の行（現状 KC 昇順ソートの素の `<tr>`、リンク/CTA なし。
      ソートは `:10`）について、低 KC 行（`black_hole`/`dim_star`）に
      `/[org]/[project]/quizzes` への「クイズで返済」CTA を付ける。
- [ ] `star-node.svelte:21-37` の星（`Tooltip.Trigger` 内の `<button>`、現状 `onclick` なし）の
      ツールチップ内容（現 33-36）に「クイズで返済」CTA を追加する。
- [ ] CTA の最小実装は `/[org]/[project]/quizzes` への素のリンクとする
      （`resolve()` で生成）。

> 補足: Quizzes ルート（`quizzes/+page.svelte`）と quiz ストアは現状
> `loadAvailable(orgSlug)`/`availableCount` のみで、**ファイル/概念フィルタ用クエリを持たない**。
> 「そのファイルで絞った quizzes」は新クエリ param + ストアフィルタが必要で **本 issue の範囲外**
> （下記「対象外・保留」）。**バックエンド不要**。

### rank 13 — データ入り Overview の主要 CTA（中 / S）

ダッシュボードの数値（既に算出済み）に「次の行動」CTA を添える。

- [ ] `overview-dashboard.svelte` の PriorityList 領域（`:58` で描画。ヘッダは
      `priority-list.svelte:28` の素の `<div>` タイトル）付近に
      「View all N danger files」CTA を置き、`/matrix?cell=danger` へ飛ばす。
      N は既に算出済みの `dangerCount`（`overview-dashboard.svelte:16-18`）を補間する。
- [ ] KC 統計カード（`overview-dashboard.svelte:33-37` の `StatCard`、`latestKc`/`kcChange` は
      `:19-21` で算出）付近に「Raise team KC」CTA を置き、`/galaxy`（または `/quizzes`）へ飛ばす。
- [ ] CTA 文言は Paraglide（ja 主・en 従）に追加。

> 補足: 遷移先は rank 4 と共通（`/matrix?cell=danger` は `matrix/+page.ts` が解釈済み）。
> **バックエンド不要**。

### rank 21 — 見た目操作可能なノードを実際に動かす（または affordance 除去）（重大 / M）

`hover:scale-150` を持つが `onclick` の無いノードは現状ちょうど 2 箇所。
**実遷移を与える**か、配線できないなら **拡大 affordance を外す**。

- [ ] `star-node.svelte:29`（`hover:scale-150` の `Tooltip.Trigger` ボタン、`onclick` なし）に
      実 onclick/CTA を与える。`FileMastery` は `path`/`module` のみで debt id が無いため
      （`star-node.svelte:8`）、`/[org]/[project]/quizzes`（rank 8 と統合）へ遷移、
      または `path` → Repos ファイル遷移が可能ならそちらへ。配線不能なら `hover:scale-150` を外す。
- [ ] `debt-matrix.svelte:61`（散布図の点、`onmouseenter`/`onmouseleave`/`onfocus`/`onblur` のみ）に
      rank 4 の遷移（`/matrix?cell=...`）を付ける。これにより hover 拡大と実挙動を一致させる。
- [ ] 上記で配線できたノードは affordance を維持、できないものは `hover:scale-150` を撤去して
      「触れるのに動かない」状態を解消する。

> 補足: 本 rank は rank 4 / 8 と意図的に重複（メタ指摘）。`debt-list-row.svelte:15` の
> `resolve()` パターンを再利用。`priority-list` の行は `scale-150` を持たない（素の span）。
> **バックエンド不要**。

### rank 23 — gap_concepts をアクション化（重大 / M）

ギャップ概念を「次に学ぶ場所」へのチップにする。**2 つの異なる形**に注意：

- クイズ結果（`constructive-result.svelte:38`）の `gap_concepts` は `Concept{id,label}`
  （`schemas.ts:324,356`）。
- 学習プラン（`learning/+page.svelte:38`）の `gap_concepts` は `string[]`
  （`schemas.ts:484`、mock は `learning-plan.ts:7`）で、join された文字列として表示。

- [ ] `constructive-result.svelte:37-39` の `gap_concepts`（現状 `<li>・{c.label}</li>`、
      リンクなし）を、`/galaxy`（または フィルタ付き `/quizzes`）へ飛ぶチップにする。
- [ ] `learning/+page.svelte:38` の `gap_concepts.join(" / ")`（プレーン文字列）を、
      各概念を `/galaxy` へのチップにレンダリングし直す。
- [ ] 遷移先はジェネリックな `/galaxy`（または フィルタ `/quizzes`）を最小実装とする。

> 補足: concept → file マッピングは **どの mock にも存在しない**
> （`galaxy.ts`/`learning-plan.ts`/`quiz-mock.ts`）。よって「その概念の特定の Galaxy star へ
> ディープリンク」はマッピングデータの追加が必要で **本 issue の範囲外**（下記「対象外・保留」）。
> 本 issue では一般的な `/galaxy` 遷移に留める。**バックエンド不要**。

### rank 24 — Matrix 負債 ↔ Agent 相互リンク（中 / M）

「検出 → 推論」を Matrix 詳細と Agents 画面の間で往復できるようにする。

- [ ] 順方向: `debt-meta-panel.svelte:14` の agent 行（現状
      `value: agentLabel(debt.assigned_agent)` の非リンク `<span>`、`23-27` で描画）を
      `/[org]/[project]/agents` へのリンクにし、`debt.kind` に応じて `agents.selectedKind`
      （`agent-store.svelte.ts:7` の `$state<AgentKind>("code_debt")`）を事前選択する。
- [ ] 逆方向: `agent-activity.ts` の `NarrativeEvidence.href`（**現状 5 件すべて `null`**：
      `:44,49,60,65,102,110`）のうち **最低 1 つ** を `/matrix/[debtId]` 詳細パスに設定し、
      死んだ逆リンクを 1 つ以上生かす。

> 補足: agents ページは `agents.selectedKind`（`agents/+page.svelte:26` の Tabs）を読むが、
> 現状 URL ではなく in-page Tabs 経由。ストアへ事前選択をセットする方式で動く
> （URL 連携は範囲外）。`agentLabel` は `matrix/labels.ts` 由来。**バックエンド不要**。

## 完了条件

- **rank 2b**: クイズ結果 CTA から Learning に来たとき（`?from=quiz`）に
  PlanProgress + ResourceList が表示され、サイドバー素遷移時のみ Coming Soon が出る。
- **rank 4 / 21**: Overview の priority-list 行・散布図の点・危険象限セル・凡例 danger 行を
  クリックすると `/matrix?cell=danger`（または該当クエリ）へ遷移し、Matrix がそのフィルタ状態で
  復元される。散布図の点の hover 拡大と実挙動が一致している。
- **rank 8**: Galaxy の `black_hole`/`dim_star` 行・星ツールチップに「クイズで返済」CTA があり、
  クリックで `/[org]/[project]/quizzes` に遷移する。
- **rank 13**: データ入り Overview に「View all N danger files」（`dangerCount` 補間）→
  `/matrix?cell=danger`、「Raise team KC」→ `/galaxy`(or `/quizzes`) の CTA が表示・遷移する。
- **rank 23**: クイズ結果と学習プランの gap_concepts がチップとしてレンダリングされ、
  クリックで `/galaxy`(or フィルタ `/quizzes`) に遷移する。
- **rank 24**: Matrix 詳細の agent 行クリックで `/agents` に遷移し、`debt.kind` に応じた
  kind が事前選択される。Agents のナラティブ証跡のうち少なくとも 1 件が Matrix 詳細へ戻れる。
- 「見た目操作可能なのに動かない」ノードが残っていない（配線 or affordance 撤去のいずれか）。
- `cd frontend && bun run check` / `bun run lint` / `bun run test:unit` がパスする。

## 対象外・保留

- **rank 8 / 23 の「ファイル/概念で絞った Quizzes・特定 star へのディープリンク」**:
  Quizzes ルート/ストア（`quizzes/+page.svelte`・quiz ストア）に file/concept フィルタ用の
  クエリ param が無く、concept → file マッピングもどの mock（`galaxy.ts`/`learning-plan.ts`/
  `quiz-mock.ts`）にも存在しない。新クエリ param + ストアフィルタ + マッピングデータの追加が
  必要なため、本 issue ではジェネリックな `/quizzes`・`/galaxy` 遷移に留め、絞り込みは後続 issue。
- **priority-list / 散布図の点から `/matrix/[debtId]` への個別ディープリンク**:
  `FileDebt`（priority-list）・`FileMastery`（star-node）が debt id を持たないため、
  個別 debt 詳細への直リンクは id マッピングが必要。本 issue ではクエリ遷移（`?cell`/`?severity`）に統一。
- **rank 24 の URL ベース kind 連携**: agents ページは現状 in-page Tabs で kind を切替えており、
  URL クエリでの kind 連携は未実装。本 issue ではストア（`agents.selectedKind`）の事前選択で配線し、
  URL 連携は範囲外とする。

## 参考

### 元レビュー rank 対応

| rank | 要点 | 状態 |
|---|---|---|
| 2b | quiz→learning ハンドオフ（`preview` 初期値） | タスク化（重大/S） |
| 4 | Overview→Matrix ディープリンク（発信側） | タスク化（重大/S） |
| 8 | Galaxy→Quizzes 接続（CTA） | タスク化（重大/M、フィルタは保留） |
| 13 | データ入り Overview の主要 CTA | タスク化（中/S） |
| 21 | 見た目操作可能ノードの実配線 / affordance 除去 | タスク化（重大/M、rank 4/8 のメタ） |
| 23 | gap_concepts のアクション化 | タスク化（重大/M、concept→file は保留） |
| 24 | Matrix 負債 ↔ Agent 相互リンク | タスク化（中/M、URL kind 連携は保留） |

### 関連 file（実在確認済み）

- 配線スイッチ
  - `frontend/src/routes/[org]/[project]/learning/+page.svelte:9`（`preview` 初期値）
  - `frontend/src/routes/[org]/[project]/learning/+page.ts:8-14`（`from` 読込済み）
- Overview（発信 affordance）
  - `frontend/src/lib/components/overview/priority-list.svelte:30-34`（行・id なし）
  - `frontend/src/lib/components/overview/debt-matrix.svelte:36,57-71`（危険セル・散布図の点）
  - `frontend/src/lib/components/overview/quadrant-legend.svelte:21-28`（danger 行）
  - `frontend/src/lib/components/overview/overview-dashboard.svelte:16-21,33-37,58`（`dangerCount`/`latestKc`/CTA 設置点）
- Matrix（復元入口・既実装 + 詳細）
  - `frontend/src/routes/[org]/[project]/matrix/+page.ts:9-32`（`cell`/`kind`/`severity` 解釈）
  - `frontend/src/routes/[org]/[project]/matrix/+page.svelte:18`（`initialFilter` seed）
  - `frontend/src/lib/components/matrix/debt-list-row.svelte:14-15`（`resolve()` パターン）
  - `frontend/src/routes/[org]/[project]/matrix/[debtId]/`（詳細ルート・逆リンク先）
- Galaxy
  - `frontend/src/lib/components/galaxy/mastery-list.svelte:10,24-41`（KC 昇順・行）
  - `frontend/src/lib/components/galaxy/star-node.svelte:8,29,33-36`（星・`hover:scale-150`・ツールチップ）
- Quiz / Learning（gap_concepts）
  - `frontend/src/lib/components/quiz/constructive-result.svelte:37-39,44`（gap 概念・learningHref CTA）
  - `frontend/src/lib/api/schemas.ts:324,356,484`（`Concept{id,label}` vs `string[]`）
  - `frontend/src/lib/mocks/learning-plan.ts:7`（plan の gap_concepts は文字列配列）
- Agents
  - `frontend/src/lib/components/matrix/debt-meta-panel.svelte:14,23-27`（agent 行・非リンク）
  - `frontend/src/lib/stores/agent-store.svelte.ts:7`（`selectedKind`）
  - `frontend/src/lib/mocks/agent-activity.ts:44,49,60,65,102,110`（`href: null` ×5+）
  - `frontend/src/routes/[org]/[project]/agents/+page.svelte:26`（Tabs で kind 切替）

### 関連 issue

- `docs/issue/013-settings-org-members-wiring.md` — API 先行・UI 未配線の解消パターン（様式参照）
- `docs/issue/018-stack-analysis-async-job-on-service.md` — 画面間配線・ストア設計の先行例（様式参照）
