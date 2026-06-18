import type { AgentActivity, AgentPipeline, AgentProfile } from "$lib/api/schemas";

// Twin Agent のモック。§4.2（考古学フェーズ）/ §6.5（ナラティブ）の例文をベースにする。
// 実エージェント連携は後続 issue。ここは UI のデータ契約を固める目的。

export const MOCK_PROFILES: AgentProfile[] = [
  {
    kind: "code_debt",
    name: "アーキ考古学者",
    role: "Code Debt Agent",
    accent: "debt-code",
    tagline: "重複と規約逸脱を掘り起こし、過去の経緯ごと返済を提案します。",
  },
  {
    kind: "knowledge_debt",
    name: "ナレッジ教師",
    role: "Knowledge Debt Agent",
    accent: "debt-knowledge",
    tagline: "誰も理解していないコードを見つけ、クイズで理解を取り戻す道を示します。",
  },
];

export const MOCK_ACTIVITIES: AgentActivity[] = [
  {
    id: "act-code-1",
    kind: "code_debt",
    headline: "utils/date.ts の重複を統合",
    pipeline_id: "pipe-code-1",
    created_at: "2026-06-17T11:00:00+09:00",
    steps: [
      {
        id: "s1",
        status: "succeeded",
        message: "3 ファイルの日付フォーマット関数の類似度を計算しました。",
        created_at: "2026-06-17T11:00:00+09:00",
        evidence: [],
      },
      {
        id: "s2",
        status: "succeeded",
        message: "重複を 3 箇所で検出しました（cosine 0.91 / 0.87）。",
        created_at: "2026-06-17T11:00:30+09:00",
        evidence: [
          { type: "first_commit", label: "helpers/time.ts 初出", detail: "2025-06 / AI 生成痕跡あり", href: null },
          {
            type: "pr_review",
            label: "PR #2456",
            detail: "本文「日付フォーマットの修正」のみ・レビューなし",
            href: null,
          },
        ],
      },
      {
        id: "s3",
        status: "succeeded",
        message: "ADR-0019 を発見しました。helpers/time.ts は ADR を参照せず再実装されています。",
        created_at: "2026-06-17T11:01:00+09:00",
        evidence: [
          {
            type: "adr_reference",
            label: "ADR-0019（date-fns で集約）",
            detail: "日付処理は utils/date.ts に集約する方針",
            href: null,
          },
          {
            type: "ai_generated",
            label: "AI 生成痕跡",
            detail: "コミット時刻分布・差分スタイルの一貫性から推定 92%",
            href: null,
          },
        ],
      },
      {
        id: "s4",
        status: "analyzing",
        message: "統合を推奨し、返済 PR の影響範囲（12 箇所のインポート）を計算中…",
        created_at: "2026-06-17T11:01:30+09:00",
        evidence: [],
      },
    ],
  },
  {
    id: "act-know-1",
    kind: "knowledge_debt",
    headline: "UserService.ts のレビューが形式的",
    pipeline_id: "pipe-know-1",
    created_at: "2026-06-17T12:00:00+09:00",
    steps: [
      {
        id: "s1",
        status: "succeeded",
        message: "UserService.ts の Knowledge Coverage を算出しました。",
        created_at: "2026-06-17T12:00:00+09:00",
        evidence: [],
      },
      {
        id: "s2",
        status: "succeeded",
        message: "KC は 23% でした。アクティブに利用される重要ファイルです。",
        created_at: "2026-06-17T12:00:20+09:00",
        evidence: [
          { type: "first_commit", label: "@bob が最終更新", detail: "git blame 上の主担当だが KC は低い", href: null },
        ],
      },
      {
        id: "s3",
        status: "succeeded",
        message: "@bob さんのレビューは形式的（所要 2 分・コメント 0 件）でした。",
        created_at: "2026-06-17T12:00:40+09:00",
        evidence: [{ type: "pr_review", label: "PR #3789", detail: "自動 approve のみ・議論なし", href: null }],
      },
      {
        id: "s4",
        status: "running_quiz",
        message: "@bob さんにクイズを提案中… 本当に理解しているか確かめましょう。",
        created_at: "2026-06-17T12:01:00+09:00",
        evidence: [],
      },
    ],
  },
];

export const MOCK_PIPELINES: AgentPipeline[] = [
  {
    id: "pipe-code-1",
    kind: "code_debt",
    stages: [
      {
        key: "detect",
        label: "検知",
        nodes: [{ id: "n1", label: "重複スキャン", status: "succeeded", retryable: false }],
      },
      {
        key: "analyze",
        label: "分析",
        nodes: [{ id: "n2", label: "考古学調査", status: "analyzing", retryable: false }],
      },
      { key: "plan", label: "計画", nodes: [{ id: "n3", label: "PR 分割計画", status: "pending", retryable: false }] },
      { key: "repay", label: "返済", nodes: [{ id: "n4", label: "返済 PR 作成", status: "failed", retryable: true }] },
      {
        key: "verify",
        label: "検証",
        nodes: [{ id: "n5", label: "CI 自己確認", status: "pending", retryable: false }],
      },
    ],
  },
  {
    id: "pipe-know-1",
    kind: "knowledge_debt",
    stages: [
      { key: "detect", label: "検知", nodes: [{ id: "n1", label: "KC 算出", status: "succeeded", retryable: false }] },
      {
        key: "analyze",
        label: "分析",
        nodes: [{ id: "n2", label: "ギャップ抽出", status: "analyzing", retryable: false }],
      },
      {
        key: "plan",
        label: "計画",
        nodes: [{ id: "n3", label: "学習プラン生成", status: "pending", retryable: false }],
      },
      {
        key: "repay",
        label: "返済",
        nodes: [{ id: "n4", label: "クイズ実施", status: "running_quiz", retryable: false }],
      },
      {
        key: "verify",
        label: "検証",
        nodes: [{ id: "n5", label: "再クイズ判定", status: "pending", retryable: false }],
      },
    ],
  },
];
