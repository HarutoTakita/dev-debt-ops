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

// 多言語対応（i18n）: アプリを英語 UI に切り替え、アカウントメニューの言語サブメニューを
// 展開した状態（English に✓）を撮影する。提出資料の i18n 説明で使う。
test("言語メニュー（英語切替）", async ({ page }) => {
  await startDemo(page);
  try {
    // 1) 日本語 UI のままメニュー → 言語サブメニューを開き、English に切り替える。
    //    言語サブメニュー（DropdownMenu.Sub）は hover で開く（bits-ui）。
    await page.locator('[data-tour="user-menu-trigger"]').click({ timeout: 10_000 });
    await page.locator('[data-tour="user-menu-language-trigger"]').hover();
    const langMenu = page.locator('[data-tour="user-menu-language"]');
    await langMenu.first().waitFor({ timeout: 10_000 });
    // setLocale(loc) が呼ばれ、Paraglide がロケール反映のためページを再読込/遷移する。
    await langMenu.getByRole("menuitem", { name: "English" }).click();
    await page.waitForLoadState("networkidle").catch(() => {});
    await page.waitForTimeout(800); // 再読込後の再描画待ち（UI が英語になる）

    // 2) 英語 UI で再度メニュー → 言語サブメニューを開いた状態を撮影する。
    //    hover のままだと閉じることがあるため、サブメニュー内（English 項目）へポインタを移して開いたまま保持する。
    await page.locator('[data-tour="user-menu-trigger"]').click({ timeout: 10_000 });
    await page.locator('[data-tour="user-menu-language-trigger"]').hover();
    await langMenu.first().waitFor({ timeout: 10_000 });
    await langMenu.getByRole("menuitem", { name: "English" }).hover();
    await page.waitForTimeout(400);
    await shot(page, "25-language-en", { title: "言語切り替え（英語 UI・言語メニュー展開）" });
  } catch (e) {
    console.warn("skip 25-language-en:", String(e));
  }
});
