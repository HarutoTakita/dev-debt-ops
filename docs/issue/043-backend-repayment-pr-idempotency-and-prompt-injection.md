# 返済 PR 生成の冪等性とプロンプトインジェクション耐性

## 概要 / 重大度

**重大度: High（非冪等な外部書き込み + 信頼境界）。**

返済 PR 生成は GitHub 書き込みを伴う唯一のパイプライン。(1) 部分失敗後の再配信で
ブランチ/コミット/PR を再作成して 422 や重複 PR を生む、(2) リポジトリ内容（攻撃者制御可能）を
そのまま Gemini プロンプトに連結し、出力 `new_content` を**検証せずコミット**する。

## 該当箇所と問題

### A. 再配信でブランチ/PR を再作成（High）
- `service/service/pipelines/repayment_pr_generation.py:73-116` — 冪等ガードは
  `debt.status=="in_pr" and debt.related_pr`。このフラグは全書き込み成功 + commit 後に立つ（:110-113）。
  PR open 後〜commit 前に再配信されると `create_branch`（`github_git_client.py:380-386`、
  "already exists" 非対応）が 422 → FAILED、PR が孤児化。逆にブランチ作成前なら重複 PR。
- **修正**: ブランチ作成を冪等化（422/既存 ref を検知して再利用）、`rosetta/repay-*` の既存 open PR を
  作成前に検知、`status="in_pr"` を書き込み前後で防御的に設定。docstring の冪等保証を実態に合わせる。

### B. プロンプトインジェクション → 自動生成 PR への混入（High）
- `service/service/services/gemini_stack_service.py:176-218`（`_REFACTOR_PROMPT`/`generate_refactor`）、
  消費は `repayment_pr_generation.py:82-105`。対象ファイル `content` と `debt.archaeology_notes`
  （リポジトリ内容由来 = PR/コミットを開ける主体が制御可能）を区切り無しで連結し、
  出力 `new_content` を**逐語コミット**、`pr_title`/`pr_body` をそのまま使用。
  細工で攻撃者指定の内容（バックドア等）を自動 PR に注入し得る。
- ブラスト半径: 書き込みは当該 project 自身の repo の新ブランチのみ・自動マージ無し・起動は admin 限定
  なので人間レビュー前提。とはいえ「もっともらしい悪性 PR」の social-engineering ベクタ。
- **修正**:
  - プロンプトに明示的な区切り（信頼境界）を入れ、リポジトリ内容は「データであって指示ではない」旨を提示。
  - 出力サイズ/差分の sanity check（変更行数の上限、対象は debt 領域に限定する方向）。
  - PR 本文に「機械生成・未レビュー」を明示（既存の 🤖 プレフィックスは維持）。
  - `new_content` 全文置換ではなくレビュー可能な patch に寄せる検討（最低限、巨大置換は拒否）。

## 受け入れ条件

- 既存ブランチ/PR がある状態での再起動が 422 で落ちず、重複 PR を作らない（テスト: mock GitHub client で
  "already exists" を返すケース）。
- `generate_refactor` の出力に対するサイズ/差分ガードのユニットテスト。
- プロンプトに信頼境界の区切りが入っていること（レビュー可能な diff）。
- backend gates（ruff/ty/pytest）緑。

## 対象外

- 自動マージ・自動レビュー（人間レビュー前提を維持）。
- 042 の汎用冪等化（本 issue は返済 PR 固有の外部書き込みに集中。042 と協調）。
