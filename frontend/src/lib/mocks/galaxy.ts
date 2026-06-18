import type { PersonalGalaxy } from "$lib/api/schemas";

// Knowledge Galaxy のモック。数モジュール（星系）× 各数ファイル（星）に、
// star / dim_star / black_hole / unexplored を混在させる。observed は store 側で true に上書きする。
export const mockGalaxy: PersonalGalaxy = {
  developer: "you",
  org_kc: 0.62,
  observed: false,
  systems: [
    {
      module: "auth",
      kc: 0.52,
      files: [
        { path: "src/auth/permissions.ts", module: "auth", kc: 0.23, mastery: "black_hole", mastered: false },
        { path: "src/auth/session.ts", module: "auth", kc: 0.55, mastery: "dim_star", mastered: false },
        { path: "src/auth/guard.ts", module: "auth", kc: 0.78, mastery: "star", mastered: true },
      ],
    },
    {
      module: "services",
      kc: 0.42,
      files: [
        { path: "src/services/user.ts", module: "services", kc: 0.31, mastery: "black_hole", mastered: false },
        { path: "src/services/order.ts", module: "services", kc: 0.48, mastery: "dim_star", mastered: false },
        { path: "src/services/notification.ts", module: "services", kc: 0.82, mastery: "star", mastered: true },
        { path: "src/services/legacy-sync.ts", module: "services", kc: 0.05, mastery: "unexplored", mastered: false },
      ],
    },
    {
      module: "utils",
      kc: 0.88,
      files: [
        { path: "src/utils/format.ts", module: "utils", kc: 0.91, mastery: "star", mastered: true },
        { path: "src/utils/date.ts", module: "utils", kc: 0.85, mastery: "star", mastered: true },
        { path: "src/utils/cn.ts", module: "utils", kc: 0.88, mastery: "star", mastered: true },
      ],
    },
    {
      module: "billing",
      kc: 0.09,
      files: [
        { path: "src/billing/invoice.ts", module: "billing", kc: 0.18, mastery: "black_hole", mastered: false },
        { path: "src/billing/tax.ts", module: "billing", kc: 0.0, mastery: "unexplored", mastered: false },
      ],
    },
    {
      module: "api",
      kc: 0.45,
      files: [
        { path: "src/api/client.ts", module: "api", kc: 0.6, mastery: "dim_star", mastered: false },
        { path: "src/api/webhooks.ts", module: "api", kc: 0.29, mastery: "black_hole", mastered: false },
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
};
