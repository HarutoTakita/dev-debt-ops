import type { LearningPlan } from "$lib/api/schemas";

// 学習プランのモック（§5.4 の例）。段階 1: チーム内資産（最優先）→ 段階 2: 外部資源候補。
// 実データ取得・Vector Search・進捗永続化は後続 issue。ここは UI レイアウト確認用。
export const mockLearningPlan: LearningPlan = {
  id: "plan-001",
  gap_concepts: ["distributed_caching", "ADR-0012", "RedisClient"],
  estimated_total_minutes: 70,
  steps: [
    {
      order: 1,
      completed: true,
      resource: {
        id: "r1",
        origin: "team",
        kind: "adr",
        title: "ADR-0012 DB 死活独立性ポリシー",
        source_ref: "ADR-0012",
        url: null,
        estimated_minutes: 10,
        priority: "required",
        dormant_days: 540, // 18 か月読まれていない（死蔵）
      },
    },
    {
      order: 2,
      completed: true,
      resource: {
        id: "r2",
        origin: "team",
        kind: "video",
        title: "勉強会「分散キャッシュ設計」",
        source_ref: "@alice 2023-Q4",
        url: null,
        estimated_minutes: 25,
        priority: "required",
        dormant_days: 210,
      },
    },
    {
      order: 3,
      completed: false,
      resource: {
        id: "r3",
        origin: "team",
        kind: "pr_comment",
        title: "PR #4523 レビュー議論",
        source_ref: "PR #4523 by @alice",
        url: null,
        estimated_minutes: 5,
        priority: "recommended",
        dormant_days: 95,
      },
    },
    {
      order: 4,
      completed: false,
      resource: {
        id: "r4",
        origin: "external",
        kind: "docs",
        title: "Redis 公式 Caching Patterns",
        source_ref: null,
        url: "https://redis.io/docs/latest/develop/use/patterns/",
        estimated_minutes: 20,
        priority: "supplementary",
      },
    },
    {
      order: 5,
      completed: false,
      resource: {
        id: "r5",
        origin: "external",
        kind: "book",
        title: '"Designing Data-Intensive Applications" Ch.7',
        source_ref: "Kleppmann",
        url: null,
        estimated_minutes: null,
        priority: "supplementary",
      },
    },
    {
      order: 6,
      completed: false,
      resource: {
        id: "r6",
        origin: "team",
        kind: "code",
        title: "RedisClient.ts を読む",
        source_ref: "src/lib/redis-client.ts",
        url: null,
        estimated_minutes: 10,
        priority: "hands_on",
      },
    },
  ],
};
