# ADR 0010: agentic 解析の「決定的＝ツール / 判断＝エージェント」境界

- ステータス: Accepted（issue 069）
- 日付: 2026-06-20

## コンテキスト

解析フローを ADK で agentic 化するにあたり、**どこを LLM エージェントの自律判断にし、どこを決定的コードに残すか**を
決める必要がある。ハッカソン審査基準（AI エージェントが中核・自律的振る舞い・"エージェントである必然性"）を満たしつつ、
**正確性・コスト・再現性**を損なわないことが論点。既存の解析パイプライン（コード負債/知識負債/KC/機能クラスタリング/
クイズ/学習/返済 PR）はすでに動作しており、これを壊さないことも要件。

## 決定

1. **決定的計算はツールとして温存する。** 複雑度・重複・dead・blame/KC・依存抽出・AI 生成推定・GitHub I/O・各 upsert は
   ADK の `FunctionTool` 互換 callable として提供し、**既存パイプラインはツールの内部実装として残す**（破壊的な書き換えはしない）。
2. **判断はエージェントに委ねる。** 「どの機能/ファイルを・どこまで・どう返済するか／なぜ」という優先順位付け・解釈・戦略を
   ADK エージェント（`LlmAgent` + `LoopAgent` + `AgentTool` + `PlanReActPlanner`）の自律判断にする。
3. **ガードレールはフレームワークで機械的に強制する。** agent callback（`before_tool` / `before_model`）による `RunBudget`、
   `LoopAgent.max_iterations` + `exit_loop`、Cloud Tasks の `timeout` / `max_attempts`、`timeout_stale_jobs`。
   「自律的に動くが、回数・トークン・時間の上限は LLM の判断に依存せず保証される」状態にする。
4. **可観測性は記録のみ。** Runner `BasePlugin` の `on_event_callback` で判断・ツール呼び出し・反復を `agent_trace` /
   `Job.result_data` に記録し、`GET /api/v1/jobs/{id}` で参照する（**専用ナラティブ UI は作らない**）。
5. **追加型で導入する。** 新 `JobType.AGENTIC_ANALYSIS` として `service.registry` に登録し、既存の `run_task` /
   Cloud Tasks 基盤の上で動かす。既存パイプライン・配信 API・各 Map は不変。

## 帰結

- 正確性・コストは決定的ツールで担保しつつ、解析の中核が自律エージェントになる（審査基準への対応）。
- `LoopAgent` は adk 2.2.0 で deprecated（→ Workflow）。当面は機能するため採用し、`# ty: ignore[deprecated]` で抑制。
  Workflow API への移行はフォローアップ。
- 実 LLM（Vertex AI）実行は live 環境で検証する。テストは `run_twin_agent` をモックし、配管・構築・ツール・予算・記録を検証する
  （`stack_analysis` のテスト方針を踏襲）。
- ツールが既存サービスを呼ぶため、`code_debts` / `knowledge_debts` / `file_kc` 等への書き込み経路と冪等性は不変。
</content>
