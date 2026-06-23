import type { PersonalGalaxy } from "$lib/api/schemas";

// Knowledge Galaxy のモック。Level 1（機能グラフ）/ Level 2（機能内ファイルグラフ）の両方を見せるため、
// 機能（feature）はディレクトリをまたぐ意味的グルーピングにしてある（機能 ≠ フォルダ）。
// observed は store 側で true に上書きする。
export const mockGalaxy: PersonalGalaxy = {
  developer: "you",
  org_kc: 0.62,
  observed: false,
  systems: [
    {
      module: "auth",
      kc: 0.52,
      files: [
        {
          path: "src/auth/permissions.ts",
          module: "auth",
          kc: 0.23,
          mastery: "black_hole",
          mastered: false,
          feature_keys: ["auth"],
        },
        {
          path: "src/auth/session.ts",
          module: "auth",
          kc: 0.55,
          mastery: "dim_star",
          mastered: false,
          feature_keys: ["auth"],
        },
        {
          path: "src/auth/guard.ts",
          module: "auth",
          kc: 0.78,
          mastery: "star",
          mastered: true,
          feature_keys: ["auth"],
        },
      ],
    },
    {
      module: "services",
      kc: 0.42,
      files: [
        {
          path: "src/services/user.ts",
          module: "services",
          kc: 0.31,
          mastery: "black_hole",
          mastered: false,
          feature_keys: ["commerce"],
        },
        {
          path: "src/services/order.ts",
          module: "services",
          kc: 0.48,
          mastery: "dim_star",
          mastered: false,
          feature_keys: ["commerce"],
        },
        {
          path: "src/services/notification.ts",
          module: "services",
          kc: 0.82,
          mastery: "star",
          mastered: true,
          feature_keys: ["commerce"],
        },
        {
          path: "src/services/legacy-sync.ts",
          module: "services",
          kc: 0.05,
          mastery: "unexplored",
          mastered: false,
          feature_keys: ["commerce"],
        },
      ],
    },
    {
      module: "utils",
      kc: 0.88,
      files: [
        {
          path: "src/utils/format.ts",
          module: "utils",
          kc: 0.91,
          mastery: "star",
          mastered: true,
          feature_keys: ["platform"],
        },
        {
          path: "src/utils/date.ts",
          module: "utils",
          kc: 0.85,
          mastery: "star",
          mastered: true,
          feature_keys: ["platform"],
        },
        {
          path: "src/utils/cn.ts",
          module: "utils",
          kc: 0.88,
          mastery: "star",
          mastered: true,
          feature_keys: ["platform"],
        },
      ],
    },
    {
      module: "billing",
      kc: 0.09,
      files: [
        {
          path: "src/billing/invoice.ts",
          module: "billing",
          kc: 0.18,
          mastery: "black_hole",
          mastered: false,
          feature_keys: ["commerce"],
        },
        {
          path: "src/billing/tax.ts",
          module: "billing",
          kc: 0.0,
          mastery: "unexplored",
          mastered: false,
          feature_keys: ["commerce"],
        },
      ],
    },
    {
      module: "api",
      kc: 0.45,
      files: [
        {
          path: "src/api/client.ts",
          module: "api",
          kc: 0.6,
          mastery: "dim_star",
          mastered: false,
          feature_keys: ["platform"],
        },
        {
          path: "src/api/webhooks.ts",
          module: "api",
          kc: 0.29,
          mastery: "black_hole",
          mastered: false,
          feature_keys: ["platform"],
        },
      ],
    },
  ],
  wormholes: [
    { from: "src/services/user.ts", to: "src/auth/permissions.ts" },
    { from: "src/auth/session.ts", to: "src/auth/permissions.ts" },
    { from: "src/services/order.ts", to: "src/services/user.ts" },
    { from: "src/api/webhooks.ts", to: "src/services/notification.ts" },
    { from: "src/billing/invoice.ts", to: "src/billing/tax.ts" },
  ],
  // Level 1: 機能ノード（ディレクトリ横断）。
  features: [
    { key: "auth", name: "認証", kc: 0.52, mastery: "dim_star", file_count: 3 },
    { key: "commerce", name: "取引（注文・課金）", kc: 0.31, mastery: "black_hole", file_count: 6 },
    { key: "platform", name: "基盤（共通・API）", kc: 0.71, mastery: "star", file_count: 5 },
  ],
  // Level 1: 機能間エッジ（ファイル依存を機能へ写像し、機能をまたぐもののみ）。
  feature_edges: [
    { from: "commerce", to: "auth" },
    { from: "platform", to: "commerce" },
  ],
};
