# ADK エージェントによるリポジトリ解析を実装する

## 概要

Google ADK (Agent Development Kit) を使い、リポジトリのテックスタック解析を
**自律的・段階的** に行うエージェントを実装する。
issue-003 の「単発 Gemini API 呼び出し」を置き換え、エージェントが自らファイルを
選択・取得・分析・保存するループを回す構成に移行する。

## 背景・目的

issue-003 の MVP 実装は固定ファイルリストを Gemini に渡すだけだが、実際には：

- リポジトリの構造はプロジェクトによって異なる（モノレポ、多言語など）
- どのファイルを読むかを LLM が動的に判断できるほうが精度が上がる
- 将来の Code Debt Agent・Knowledge Debt Agent との連携には「ツールを使って自律的に動く」基盤が必要

ADK は Google の OSS エージェントフレームワーク（Claude Agent SDK や OpenAI Agents SDK と同じカテゴリ）で、`@tool` デコレーターで任意の Python 関数をツール化し、Gemini が自律的に呼び出す構成を作れる。仕様書 §8.1 でも ADK は必須技術として明記されている。

## タスク

### 環境セットアップ

- [ ] `backend/pyproject.toml` に `google-adk>=0.4.0` を追加する
- [ ] `backend/app/core/config.py` に `GEMINI_MODEL: str` 設定を追加する（デフォルト: `gemini-2.0-flash`）

### エージェント実装（`backend/app/agent/stack_agent.py`）

- [ ] 以下の ADK ツールを実装する

  | ツール | 処理 |
  |---|---|
  | `list_key_files(owner, repo, branch)` | ファイルツリーを取得し、解析対象候補（設定ファイル・CI定義等）をフィルタして返す |
  | `read_file(owner, repo, path, ref)` | 指定ファイルの内容を GitHub API 経由で取得する |
  | `classify_stack(files_content)` | 取得したファイル内容から技術スタックを JSON で分類する（Gemini 直接呼び出し） |
  | `save_stack(owner, repo, branch, result)` | 分析結果を `tech_stacks` テーブルに保存する |

- [ ] `StackAnalysisAgent` を ADK の `Agent` クラスで定義する

  ```python
  from google.adk.agents import Agent

  stack_agent = Agent(
      model="gemini-2.0-flash",
      name="stack_analysis_agent",
      instruction="""
      あなたはリポジトリのテックスタックを解析するエージェントです。
      1. list_key_files でリポジトリの設定ファイル群を取得する
      2. 重要そうなファイルを read_file で取得する（最大 10 ファイル）
      3. classify_stack でテックスタックを分類する
      4. save_stack で結果を保存する
      """,
      tools=[list_key_files, read_file, classify_stack, save_stack],
  )
  ```

### API エンドポイント更新（`backend/app/api/v1/stack.py`）

- [ ] `POST /api/v1/github/repositories/{owner}/{repo}/analyze-stack` の内部実装を
  ADK エージェント呼び出しに切り替える

  ```python
  from google.adk.runners import Runner

  runner = Runner(agent=stack_agent, ...)
  async for event in runner.run_async(
      user_id=str(current_user.id),
      session_id=f"{owner}/{repo}",
      new_message=Content(parts=[Part(text=f"owner={owner}, repo={repo}, branch={branch}")]),
  ):
      if event.is_final_response():
          return parse_result(event)
  ```

- [ ] エージェントの実行ログ（呼び出したツール・判断の根拠）をレスポンスに含める
  （`agent_trace: list[str]` フィールドを追加）

### テスト

- [ ] `tests/agent/test_stack_agent.py` を作成する
  - 各ツールのユニットテスト（GitHub API はモック化）
  - エージェント全体の統合テスト（モックリポジトリで実行）

## 完了条件

- `POST /api/v1/github/repositories/{owner}/{repo}/analyze-stack` 呼び出し時に
  ADK エージェントが起動し、複数ツールを自律的に呼び出してスタック分析が完了すること
- ログ・トレース（どのファイルを取得し、なぜそう判断したか）がレスポンスに含まれること
- issue-003 の `GET /api/v1/github/repositories/{owner}/{repo}/stack` で
  エージェントが保存した結果が取得できること
- テストがパスすること

## 技術詳細

### ADK の基本構造

```
Runner
  └── Agent (Gemini 2.0 Flash)
        ├── Tool: list_key_files   → GitHubGitClient.get_repository_tree()
        ├── Tool: read_file        → GitHubGitClient.get_file_content()
        ├── Tool: classify_stack   → genai.Client.generate_content() (JSON mode)
        └── Tool: save_stack       → TechStack DB モデル
```

### 解析対象ファイルの優先順位

```python
KEY_FILE_PATTERNS = [
    "package.json", "pyproject.toml", "go.mod", "Cargo.toml", "pom.xml",
    "requirements.txt", "Gemfile",
    "Dockerfile", "docker-compose.yml", "compose.yml",
    ".github/workflows/*.yml",
    "*.tf", "terraform.tfvars",
    "k8s/*.yaml", "kubernetes/*.yaml",
    "*.bicep",
    "vitest.config.*", "jest.config.*", "pytest.ini",
]
```

### issue-003 との関係

| 項目 | issue-003（MVP） | 本 issue（ADK） |
|---|---|---|
| ファイル選択 | 固定リスト | エージェントが動的に判断 |
| Gemini 呼び出し | 1回（全ファイル一括） | ツールとして分離・複数回可能 |
| 実行トレース | なし | `agent_trace` フィールドに記録 |
| 拡張性 | 低い | ツール追加で機能拡張可能 |

本 issue は issue-003 の `POST analyze-stack` エンドポイントの **内部実装を置き換える**もので、API インターフェースは維持する。

### 参考

- [Google ADK ドキュメント](https://google.github.io/adk-docs/)
- [ADK Python SDK](https://github.com/google/adk-python)
- `app_ref/ptw-respec/services/api/` — 参考実装（LangChain ベース。ADK の場合は構造は同様）
