import type { FileDebt, Overview } from "$lib/api/schemas";

// 観測台のモックデータ。集計バックエンド未実装のため、UI の形を見せる目的で使う。
// 数値は仕様書 §11 デモシナリオに整合させる:
//   - 幕 5: 4 週間で コード負債 67→58 / KC 44%→68%
//   - 幕 2: 左下の最危険ゾーンに 23 ファイル
// 決定的に生成する（Math.random は使わない）。

const LANGS = ["ts", "js", "py", "go"];

// 最危険ゾーン（左下: code_debt > 0.5 かつ KC < 0.5）。視線誘導のため多めに配置。
const namedDanger: FileDebt[] = [
  {
    path: "src/auth/permissions.ts",
    language: "ts",
    code_debt_score: 0.82,
    knowledge_coverage: 0.21,
    business_impact: 0.9,
    priority: "P0",
  },
  {
    path: "src/services/user-service.ts",
    language: "ts",
    code_debt_score: 0.74,
    knowledge_coverage: 0.35,
    business_impact: 0.7,
    priority: "P1",
  },
];

// 名前付き 2 件 + 生成 21 件 = 最危険 23 件（§11 幕 2）。
const generatedDanger: FileDebt[] = Array.from({ length: 21 }, (_, i) => ({
  path: `src/legacy/module-${String(i + 1).padStart(2, "0")}.ts`,
  language: LANGS[i % LANGS.length],
  code_debt_score: 0.58 + ((i * 13) % 10) * 0.035, // 0.58..0.90
  knowledge_coverage: 0.06 + ((i * 7) % 9) * 0.04, // 0.06..0.38
  business_impact: 0.3 + ((i * 5) % 7) * 0.1,
  priority: i % 4 === 0 ? "P0" : "P1",
}));

// 他象限（理想 / コード返済 / 返済余地あり）。
const others: FileDebt[] = [
  // 理想（右上: clean × 皆理解）
  {
    path: "src/lib/utils.ts",
    language: "ts",
    code_debt_score: 0.18,
    knowledge_coverage: 0.88,
    business_impact: 0.3,
    priority: "P3",
  },
  {
    path: "src/lib/cn.ts",
    language: "ts",
    code_debt_score: 0.12,
    knowledge_coverage: 0.82,
    business_impact: 0.2,
    priority: "P3",
  },
  {
    path: "src/routes/+layout.svelte",
    language: "svelte",
    code_debt_score: 0.24,
    knowledge_coverage: 0.76,
    business_impact: 0.4,
    priority: "P3",
  },
  {
    path: "src/lib/api/client.ts",
    language: "ts",
    code_debt_score: 0.28,
    knowledge_coverage: 0.7,
    business_impact: 0.6,
    priority: "P2",
  },
  // コード返済（左上: clean だが誰も理解していない / 要ナレッジ）
  {
    path: "src/lib/api/generated-types.ts",
    language: "ts",
    code_debt_score: 0.2,
    knowledge_coverage: 0.26,
    business_impact: 0.5,
    priority: "P2",
  },
  {
    path: "src/lib/config/nav.ts",
    language: "ts",
    code_debt_score: 0.16,
    knowledge_coverage: 0.33,
    business_impact: 0.4,
    priority: "P2",
  },
  // 返済余地あり（右下: 汚いが皆理解している）
  {
    path: "src/routes/[org]/repos/+page.svelte",
    language: "svelte",
    code_debt_score: 0.63,
    knowledge_coverage: 0.72,
    business_impact: 0.5,
    priority: "P2",
  },
  {
    path: "src/lib/components/repo/file-viewer.svelte",
    language: "svelte",
    code_debt_score: 0.57,
    knowledge_coverage: 0.64,
    business_impact: 0.4,
    priority: "P2",
  },
];

export const overviewMock: Overview = {
  org: "demo",
  generated_at: "2026-06-18T09:00:00+09:00",
  granularity: "file",
  features: [],
  files: [...namedDanger, ...generatedDanger, ...others],
  trend: [
    { week: "4週前", code_debt_score: 0.67, knowledge_coverage: 0.44 },
    { week: "3週前", code_debt_score: 0.64, knowledge_coverage: 0.5 },
    { week: "2週前", code_debt_score: 0.61, knowledge_coverage: 0.59 },
    { week: "今週", code_debt_score: 0.58, knowledge_coverage: 0.68 },
  ],
  activity: {
    code_agent_prs: 12,
    code_agent_merged: 9,
    knowledge_agent_quizzes: 23,
    knowledge_agent_passed: 17,
  },
};
