import { test } from "@playwright/test";
import { shot, startDemo, BASE } from "./helpers";

/**
 * 確認クイズの受験フロー（学習ハブの「理解度を確認する」→ 集中モードで受験 → 採点結果）を撮影する。
 * デモは「2 問の理解度チェックを最後まで解ける」状態でシードされている（seed_demo）。
 * UI 操作依存のため best-effort。失敗してもスイート全体は止めない。
 */
test("クイズ受験フローを撮影（best-effort）", async ({ page }) => {
  await startDemo(page);

  try {
    // 統合ハブの「理解度を確認する」= クイズセッション（/quizzes/:sessionId）への導線。
    await page.goto(`${BASE}/learning`);
    await page.getByRole("link", { name: "理解度を確認する" }).first().click({ timeout: 10_000 });
    await page.waitForURL(/\/quizzes\/[^/]+$/, { timeout: 10_000 });
    await shot(page, "09-quiz-session", { title: "クイズ受験（集中モード）" });

    // 「次へ」を辿り、最後に「提出する」で採点結果へ遷移する。
    for (let i = 0; i < 12; i++) {
      if (/\/result$/.test(page.url())) break;
      const submit = page.getByRole("button", { name: "提出する" });
      const next = page.getByRole("button", { name: "次へ" });
      if (await submit.count()) await submit.first().click();
      else if (await next.count()) await next.first().click();
      else break;
      await page.waitForTimeout(400);
    }

    await page.waitForURL(/\/result$/, { timeout: 10_000 }).catch(() => {});
    if (/\/result$/.test(page.url())) {
      await shot(page, "10-quiz-result", { title: "クイズ採点結果（理解度の更新）", fit: true });
    }
  } catch (e) {
    console.warn("skip quiz flow:", String(e));
  }
});
