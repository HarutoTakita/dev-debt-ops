import { test } from "@playwright/test";
import { shot, startDemo, ORG, BASE } from "./helpers";

/**
 * DevDebtOps の主要ページを 1 ページ 1 枚で撮影する（仕様書兼取扱説明書の素材）。
 * すべてシード済みデモ org（demo / sample-shop）に対する読み取り中心の撮影。
 */

// 直接遷移で確実に撮れるページ（一覧・概要系）。
// 注: /quizzes は /learning?tab=quiz へ 308 リダイレクトされる統合ハブなので個別には撮らない（= 07-learning）。
const PAGES: [key: string, route: string, title: string][] = [
  ["02-org-dashboard", `/${ORG}`, "組織ダッシュボード（プロジェクト一覧）"],
  ["03-overview", BASE, "プロジェクト概要 / 解析ラン・コックピット"],
  ["04-matrix", `${BASE}/matrix`, "コード品質マップ（二軸マトリクス）"],
  ["06-galaxy", `${BASE}/galaxy`, "Knowledge Galaxy（理解度マップ）"],
  ["07-learning", `${BASE}/learning`, "クイズと学習（統合ハブ）"],
  ["12-settings", `${BASE}/settings`, "プロジェクト設定"],
];

test("主要ページを撮影", async ({ page }) => {
  await startDemo(page);
  for (const [key, route, title] of PAGES) {
    await page.goto(route);
    await shot(page, key, { title, route, fullPage: true });
  }
});

// 動的 ID を含む詳細ページ（一覧から最初の項目を開く）。データ依存のため best-effort。
test("詳細ページを撮影（best-effort）", async ({ page }) => {
  await startDemo(page);

  // 負債の詳細（matrix の行 → /matrix/:id）
  try {
    await page.goto(`${BASE}/matrix`);
    await page.locator('a[href*="/matrix/"]').first().click({ timeout: 10_000 });
    await page.waitForURL(/\/matrix\/[^/]+$/, { timeout: 10_000 });
    await shot(page, "05-matrix-detail", { title: "負債の詳細（返済プラン・担当）", fullPage: true });
  } catch (e) {
    console.warn("skip 05-matrix-detail:", String(e));
  }

  // コード学習ウォークスルー: learning ハブ → 「学習を開く」でプランを開く → コード資源 → /learning/code/:id
  try {
    await page.goto(`${BASE}/learning`);
    await page.getByRole("link", { name: "学習を開く" }).first().click({ timeout: 10_000 });
    await page.waitForURL(/planId=/, { timeout: 10_000 });
    await page.locator('a[href*="/learning/code/"]').first().click({ timeout: 10_000 });
    await page.waitForURL(/\/learning\/code\//, { timeout: 10_000 });
    await shot(page, "08-learning-code", { title: "コード学習ウォークスルー", fullPage: true });
  } catch (e) {
    console.warn("skip 08-learning-code:", String(e));
  }

  // コード改善（/repos）: ?path で指摘ファイルを開いた状態（ツリー + ファイル + 負債パネル）。
  // デモは github.py のデモ対応でツリー/内容を seed から返す。
  try {
    await page.goto(`${BASE}/repos?path=src/checkout/payment.py`);
    await page.waitForTimeout(1500); // ツリー取得 → ?path 自動選択 → ファイル内容取得
    await shot(page, "11-repos", { title: "コード改善（ファイルツリー + 負債）", fullPage: true });
  } catch (e) {
    console.warn("skip 11-repos:", String(e));
  }
});
