import { test } from "@playwright/test";
import { shot, startDemo, BASE } from "./helpers";

/**
 * アプリのクローム/UI（デモで撮れるもの）: 理解度マップのリスト表示・ヘルプメニュー・
 * オンボーディングガイド・変更履歴(CHANGELOG)。すべてクライアント側 UI でデモログインのまま撮れる。
 * UI 操作依存のため best-effort。
 *
 * デスクトップ専用のクローム（サイドバーのヘルプ/セクション、コマンドパレット ⌘K トリガ等）が中心で、
 * モバイルでは非表示/ドロワー化されるため、mobile プロジェクトではスキップする（レスポンシブ版は
 * 主要ページ pages.spec / quiz.spec で撮る）。
 */
// eslint-disable-next-line no-empty-pattern -- Playwright は fixtures 引数に分割代入パターンを要求する
test.beforeEach(async ({}, testInfo) => {
  test.skip(testInfo.project.name === "mobile", "デスクトップ専用クロームのためモバイルでは撮影しない");
});

// 理解度マップ（galaxy）の「リスト」タブ表示。
test("理解度マップのリスト表示", async ({ page }) => {
  await startDemo(page);
  await page.goto(`${BASE}/galaxy`);
  try {
    await page.locator('[data-tour="galaxy-tab-list"]').click({ timeout: 10_000 });
    await page.waitForTimeout(400);
    await shot(page, "13-galaxy-list", {
      title: "理解度マップ（リスト表示）",
      route: `${BASE}/galaxy`,
      fit: true,
    });
  } catch (e) {
    console.warn("skip 13-galaxy-list:", String(e));
  }
});

// ヘルプメニュー（サイドバー下部「ヘルプ」のドロップダウン）。
test("ヘルプメニュー", async ({ page }) => {
  await startDemo(page);
  await page.goto(BASE);
  try {
    await page.locator('[data-tour="help"]').click({ timeout: 10_000 });
    await page.getByRole("menuitem", { name: "オンボーディングガイドを確認する" }).waitFor({ timeout: 10_000 });
    await shot(page, "14-help-menu", { title: "ヘルプメニュー", route: BASE });
  } catch (e) {
    console.warn("skip 14-help-menu:", String(e));
  }
});

// オンボーディングガイド（プロダクトツアー）。ヘルプ → 「オンボーディングガイドを確認する」で起動。
test("オンボーディングガイド", async ({ page }) => {
  await startDemo(page);
  await page.goto(BASE);
  try {
    await page.locator('[data-tour="help"]').click({ timeout: 10_000 });
    await page.getByRole("menuitem", { name: "オンボーディングガイドを確認する" }).click({ timeout: 10_000 });
    await page.waitForTimeout(900); // ツアーのスポットライト/ポップオーバー描画を待つ
    await shot(page, "15-onboarding-tour", { title: "オンボーディングガイド（ツアー）", route: BASE });
  } catch (e) {
    console.warn("skip 15-onboarding-tour:", String(e));
  }
});

// 新規プロジェクト作成モーダル（リポジトリ選択 → 名前 + 解析対象ブランチ選択）。
// デモは github.py のデモ対応で listRepositories / listBranches がサンプルを返す。
test("新規プロジェクト作成（repo + ブランチ選択）", async ({ page }) => {
  await startDemo(page);
  await page.goto(BASE);
  try {
    await page.getByRole("button", { name: "新規プロジェクト" }).first().click({ timeout: 10_000 });
    // repo 一覧 → 先頭 repo を選ぶと、名前入力 + 解析対象ブランチ選択の画面になる。
    await page.getByText("devdebtops/sample-shop").first().click({ timeout: 10_000 });
    await page.getByText("解析対象ブランチ").first().waitFor({ timeout: 10_000 });
    await shot(page, "18-new-project", {
      title: "新規プロジェクト作成（リポジトリ + 解析対象ブランチ選択）",
      route: BASE,
    });
  } catch (e) {
    console.warn("skip 18-new-project:", String(e));
  }
});

// 解析ステータス（トップバー「解析」ボタンのポップオーバー = 解析ラン・コックピット）。案1: 既存の状態表示。
test("解析ステータス", async ({ page }) => {
  await startDemo(page);
  await page.goto(BASE);
  try {
    await page.locator('[data-tour="analysis-run"]').click({ timeout: 10_000 });
    await page.waitForTimeout(800); // ポップオーバー + コックピット描画
    await shot(page, "19-analysis-status", { title: "解析ステータス（解析ラン・コックピット）", route: BASE });
  } catch (e) {
    console.warn("skip 19-analysis-status:", String(e));
  }
});

// コマンドパレット（⌘K / Ctrl+K 検索）。トップバーの「検索 / コマンド」からも開く。
test("コマンドパレット（⌘K 検索）", async ({ page }) => {
  await startDemo(page);
  await page.goto(BASE);
  try {
    await page.keyboard.press("ControlOrMeta+k");
    // 開かない環境向けフォールバック: トップバーの検索トリガーをクリック。
    const dialog = page.getByRole("dialog");
    if (!(await dialog.count())) {
      await page.getByRole("button", { name: /検索/ }).first().click({ timeout: 5_000 });
    }
    await dialog.first().waitFor({ timeout: 10_000 });
    await page.waitForTimeout(400);
    await shot(page, "20-command-palette", { title: "コマンドパレット（⌘K 検索）", route: BASE });
  } catch (e) {
    console.warn("skip 20-command-palette:", String(e));
  }
});

// 変更履歴（CHANGELOG）モーダル。ヘルプ → 「バージョン」で開く。
test("変更履歴(CHANGELOG)", async ({ page }) => {
  await startDemo(page);
  await page.goto(BASE);
  try {
    await page.locator('[data-tour="help"]').click({ timeout: 10_000 });
    await page.getByRole("menuitem", { name: "バージョン" }).click({ timeout: 10_000 });
    await page.waitForTimeout(600); // ダイアログ + CHANGELOG fetch
    await shot(page, "16-changelog", { title: "変更履歴（CHANGELOG）", route: BASE });
  } catch (e) {
    console.warn("skip 16-changelog:", String(e));
  }
});
