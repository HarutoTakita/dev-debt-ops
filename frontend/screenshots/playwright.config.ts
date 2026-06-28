import { defineConfig } from "@playwright/test";

/**
 * スクリーンショット取得専用の Playwright 設定（e2e の playwright.config.ts とは独立）。
 *
 * - 既に起動済みのスタックを対象にする（webServer は持たない）。
 *   デフォルトは frontend 開発サーバー（:5173 / /api は :8000 にプロキシ）。
 *   本番モードのローカルスタックを使う場合は `BASE_URL=http://localhost:8080` を指定。
 * - 認証はデモログイン。バックエンドで DEMO_MODE_ENABLED=true + seed_demo が前提（README.md）。
 *
 * 実行: `bun run screenshots`（= playwright test -c screenshots/playwright.config.ts）
 */
export default defineConfig({
  testDir: ".",
  testMatch: "**/*.spec.ts",
  // 直列実行: 1 つのデモ org / 共有デモユーザーを撮影するため、並列はクッキー・状態で競合する。
  workers: 1,
  timeout: 60_000,
  reporter: [["list"]],
  use: {
    baseURL: process.env.BASE_URL ?? "http://localhost:5173",
    viewport: { width: 1440, height: 900 },
    // 2x（Retina 相当）で撮影し高解像度の PNG を出力する。
    deviceScaleFactor: 2,
    // ダークモードで撮影する。アプリは defaultMode="dark"（+layout.svelte）だが mode-watcher は
    // システム設定に追従するため、Playwright 既定の light エミュレーションだと light になる。
    // ここで system preference を dark に揃えることで確実にダークで撮れる。
    colorScheme: "dark",
    locale: "ja-JP",
    // 撮影失敗の調査用。
    screenshot: "off",
    trace: "off",
  },
});
