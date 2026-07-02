import { test } from "@playwright/test";
import { shot, startDemo, ORG } from "./helpers";

/**
 * サイドバーのプロジェクト整理（スター付き + ユーザー定義セクション）の専用ショット。
 * グループ状態は startDemo() が全画面共通で localStorage に投入する（helpers.applyProjectSections）。
 * ここでは org ルート（どのプロジェクトも展開されず、全グループがコンパクトに並ぶ）で1枚撮る。
 * デスクトップ専用サイドバー（モバイルはドロワー）のため mobile プロジェクトではスキップ。
 */
// eslint-disable-next-line no-empty-pattern -- Playwright は fixtures 引数に分割代入パターンを要求する
test.beforeEach(async ({}, testInfo) => {
  test.skip(testInfo.project.name === "mobile", "デスクトップ専用サイドバーのためモバイルでは撮影しない");
});

test("プロジェクトのセクション/スター分け", async ({ page }) => {
  await startDemo(page);
  await page.goto(`/${ORG}`);
  await shot(page, "17-project-sections", { title: "プロジェクトのセクション分け / スター", route: `/${ORG}` });
});
