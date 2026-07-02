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
 *
 * 2 プロジェクトで撮影する:
 * - `desktop` … PC 版（1440x900）。画像は docs/取扱説明書/images/screens/ に出力。
 * - `mobile`  … モバイル(レスポンシブUI)版（390x844, isMobile）。画像は images/screens-mobile/ に出力。
 *   出力先/manifest の振り分けは helpers.ts が「ビューポート幅」で自動判定する。デスクトップ専用の
 *   クローム（サイドバー/コマンドパレット等）を撮る ui.spec / sidebar.spec は mobile ではスキップする。
 * ブラウザは chromium のみ（isMobile は chromium 専用）。iPhone 等の webkit デバイスプリセットは使わない。
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
    // ダークモードで撮影する。アプリは defaultMode="dark"（+layout.svelte）だが mode-watcher は
    // システム設定に追従するため、Playwright 既定の light エミュレーションだと light になる。
    // ここで system preference を dark に揃えることで確実にダークで撮れる。
    colorScheme: "dark",
    locale: "ja-JP",
    // 撮影失敗の調査用。
    screenshot: "off",
    trace: "off",
  },
  projects: [
    {
      name: "desktop",
      // 2x（Retina 相当）で高解像度の PNG を出力する。
      use: { viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 },
    },
    {
      name: "mobile",
      // スマホ相当のビューポート＋モバイルエミュレーション（chromium 専用）。レスポンシブUIを撮る。
      use: { viewport: { width: 390, height: 844 }, deviceScaleFactor: 3, isMobile: true, hasTouch: true },
    },
  ],
});
