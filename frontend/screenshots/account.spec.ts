import { test } from "@playwright/test";
import { shot, startDemo } from "./helpers";

/**
 * アカウント/管理系のクローム（デモで撮れるもの）: アカウントメニュー（右上アバター）・
 * アカウント画面（/account）・管理ダッシュボード（/admin）・キーボードショートカット一覧（?）。
 *
 * デモユーザーは管理者想定の UI になり /admin を閲覧できる（issue 069。表示は架空のサンプルメンバーのみ、
 * クレジット付与は読み取り専用）。UI 操作依存のため best-effort。
 *
 * デスクトップ専用クローム（アバターメニュー・ショートカット等）が中心のため mobile ではスキップする。
 */
// eslint-disable-next-line no-empty-pattern -- Playwright は fixtures 引数に分割代入パターンを要求する
test.beforeEach(async ({}, testInfo) => {
  test.skip(testInfo.project.name === "mobile", "デスクトップ専用クロームのためモバイルでは撮影しない");
});

// アカウントメニュー（右上アバターのドロップダウン: 言語 / テーマ / アカウント / ユーザー管理 / ログアウト）。
test("アカウントメニュー", async ({ page }) => {
  await startDemo(page);
  try {
    await page.locator('[data-tour="user-menu-trigger"]').click({ timeout: 10_000 });
    await page.getByRole("menuitem", { name: "アカウント" }).first().waitFor({ timeout: 10_000 });
    await page.waitForTimeout(300);
    await shot(page, "21-account-menu", { title: "アカウントメニュー（言語・テーマ・ログアウト）" });
  } catch (e) {
    console.warn("skip 21-account-menu:", String(e));
  }
});

// アカウント画面（/account: メール・ロール・残りの解析クレジット）。全ユーザー向け。
test("アカウント画面", async ({ page }) => {
  await startDemo(page);
  try {
    await page.goto("/account");
    await page.waitForLoadState("networkidle").catch(() => {});
    await shot(page, "22-account", { title: "アカウント画面（残りの解析クレジット）", route: "/account", fit: true });
  } catch (e) {
    console.warn("skip 22-account:", String(e));
  }
});

// 管理ダッシュボード（/admin: ユーザー管理・クレジット付与・メンバー活動の可視化）。管理者/デモのみ。
test("管理ダッシュボード", async ({ page }) => {
  await startDemo(page);
  try {
    await page.goto("/admin");
    await page.waitForLoadState("networkidle").catch(() => {});
    await shot(page, "23-admin", {
      title: "管理者向け機能（ユーザー管理・クレジット付与）",
      route: "/admin",
      fit: true,
    });
  } catch (e) {
    console.warn("skip 23-admin:", String(e));
  }
});

// キーボードショートカット一覧（? キーで開く Dialog）。
test("キーボードショートカット一覧", async ({ page }) => {
  await startDemo(page);
  try {
    // ? のハンドラは `<svelte:window onkeydown>` で window の keydown を購読する（e.key === "?"）。
    // ヘッドレスではキーボード配列由来で "?" が届かないことがあるため、window に直接 keydown を dispatch する。
    await page.evaluate(() => window.dispatchEvent(new KeyboardEvent("keydown", { key: "?", bubbles: true })));
    const dialog = page.locator('[data-tour="shortcut-list"]');
    await dialog.first().waitFor({ timeout: 10_000 });
    await page.waitForTimeout(300);
    await shot(page, "24-shortcuts", { title: "キーボードショートカット一覧" });
  } catch (e) {
    console.warn("skip 24-shortcuts:", String(e));
  }
});
