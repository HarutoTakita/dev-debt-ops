# 解析: クイズ採点・学習プラン・クイズ生成の精度

## 概要 / 重大度

**重大度: High〜Medium。** ユーザー体験に直結する生成物（クイズ採点結果・学習プランの解説・クイズ設問）の
精度バグを是正する。A〜C は「正答が誤答になる」「解説がまるごと消える」「スコアが水増しされる」など、
理解度（KC）計測の信頼性を損なう確定バグ。

解析パイプライン横断レビュー（2026-07）由来。関連: #073, #075–#078。
確認度: **確認済**＝実コードで確認 / **要確認**＝実装前に再検証。

## 該当箇所と問題

### A. 複数選択クイズの正答が完全一致比較で誤判定される（High・確認済）
- **該当**: `service/service/pipelines/quiz_grading.py:34-44`（`_choice_matches`）、
  API 側ミラー `api/app/api/v1/quizzes.py:96-99`（`_answer_correct`）
- **問題**: `expected` が Python `list` のときだけ集合比較。だが生成クイズの解答キーは**カンマ文字列**
  （例 `"a,c"`。`gemini_stack_service` の生成プロンプト / エージェントスキーマがそう指示）で保存されるため
  `else` の**完全一致比較** `str(given).strip() == str(expected)` に落ちる。フロントは
  `[...].sort().join(",")`（`answer-input.svelte`）で保存するので、LLM が id を未ソート（`"c,a"`）や
  空白付き（`"a, c"`）で出すと**満点回答が誤答**に → KC を過小認定（`file_kc` の習得度に波及）。
- **修正**: multiple_select（またはどちらかにカンマ含有）は両辺を
  `{p.strip() for p in str(x).split(",") if p.strip()}` の集合に正規化して比較。単一選択側も `expected` を `.strip()`。

### B. 解答キー欠落の設問が分母から消えスコアが水増しされる（Medium・確認済）
- **該当**: `service/service/pipelines/quiz_grading.py:61-73`（`_grade_offline`）
- **問題**: `answer_key.get(qid)` が dict でない / `answer` が None の設問は `total += 1` せず `continue`。
  生成 answer_key の qid が設問 id とズレる（qid 欠落、`"1"` vs `"q1"`）と、キーが 1 問しか無ければ
  `total=1` → 1 問正解で 100%、0 問なら `total=0` → 0.0。この虚偽スコアが習得度として `file_kc` に書かれる。
- **修正**: 生成時に全設問 id にキーがあることを検証（不足は補修/reject）。採点時は欠落キーを
  「不正解として計上」（少なくとも `total < len(questions)` を warn/surface）。

### C. 学習プランがパス完全一致で Gemini の解説を全落ちさせる（High・確認済）
- **該当**: `service/service/pipelines/learning_plan_generation.py:134-174`（`_code_resources`）
- **問題**: ステップ採用条件が `s["source_ref"] in set(code_files)` の**完全一致**のみ。モデルが `./` 付き・
  区切り違い・repo 相対/feature 相対の差でパスを返すと**全ステップ破棄** → `summary=""` のファイル一覧
  フォールバック（:158）に降格し、学習者は Gemini の「何を/なぜ」を全て失う（無言劣化）。
- **修正**: 両辺を正規化（先頭 `./` 除去・区切り統一）してから membership 判定、加えて basename/suffix
  フォールバック一致で near-miss を救済。

### D. 空コンテキストからの幻覚クイズ（Medium・要確認）
- **該当**: `service/service/pipelines/quiz_generation.py:51-57, 104-108`（`_feature_content`）、
  到達経路 `baseline_generation.py:119`
- **問題**: 機能に FeatureFile が無い/取得が空だと `content` が「Feature 名 + 説明」だけに退化。Gemini は
  見ていないファイルから必須の `code_snippet` を複写指示され、**存在しないファイル参照/根拠なし設問**を生成。
  実コードが入ったことを保証するガードが無い。
- **修正**: 非空のファイルブロックが 1 つも組めなければ当該機能のクイズ生成をスキップ（再試行 / insufficient
  マーク）。

### E. per-file 3000 字カットに truncation マーカーが無い（Low・要確認）
- **該当**: `service/service/pipelines/quiz_generation.py:54`
- **問題**: `(fc.content or '')[:_MAX_FEATURE_FILE_CHARS]` が行途中で切れ、`gemini_stack_service._build_file_section`
  （`"... (truncated)"` を付す）と違い**続きがある signal を与えない**。カット後方のロジック参照や、
  切れた先の verbatim `code_snippet` 指示で grounding が劣化。
- **修正**: クリップ時に `"\n... (truncated)"` を付す。可能なら代表シンボル周辺を優先抽出。

### F. walkthrough の `start_text` 再アンカーが誤爆する（Low・要確認）
- **該当**: `service/service/services/code_walkthrough.py:53-61`（`clean_steps`）
- **問題**: 同一行（`return None` / `}` / `})`）が複数あると LLM が申告した（=信用できない）`start` に最も近い
  一致を選ぶため、無関係ブロックをハイライトしうる。`start_text` が一致しないとクランプ済みの生行番号を保持
  （本モジュール自身が LLM は行番号を誤ると注記）。
- **修正**: アンカー一致は一意 or 申告近傍の小窓に限定。曖昧/不在ならそのステップを落とす。

## 受け入れ条件

- A: 未ソート/空白付きの複数選択回答が正しく採点される（テスト。API ミラーも修正）。
- B: 解答キー欠落設問が分母に計上される／生成時に全設問キーを検証（テスト）。
- C: `./` 付き等のパス差でも解説が保持される（正規化 + フォールバック一致のテスト）。
- D: 空コンテキストの機能はクイズ生成をスキップする（テスト）。
- backend gates 緑。

## 対象外

- クイズ難易度設計・出題数の再設計、walkthrough の抜本改修。
