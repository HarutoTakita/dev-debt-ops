import { test } from "@playwright/test";
import { shot, startDemo, ORG } from "./helpers";

/**
 * サイドバーのプロジェクト整理（スター付き + ユーザー定義セクション）の専用ショット。
 * グループ状態は startDemo() が全画面共通で localStorage に投入する（helpers.applyProjectSections）。
 * ここでは org ルート（どのプロジェクトも展開されず、全グループがコンパクトに並ぶ）で1枚撮る。
 */
test("プロジェクトのセクション/スター分け", async ({ page }) => {
  await startDemo(page);
  await page.goto(`/${ORG}`);
  await shot(page, "17-project-sections", { title: "プロジェクトのセクション分け / スター", route: `/${ORG}` });
});
