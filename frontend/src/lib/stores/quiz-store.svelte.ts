import { listQuizzes, saveQuizAnswer } from "$lib/api/client";
import type { QuizAnswer, QuizListItem } from "$lib/api/schemas";

// クイズ返済体験のストア（Svelte 5 クラスベース runes）。
// 一覧取得と途中保存（PATCH upsert）を実 API で配線（issue 034）。採点は result ローダで実行。
class QuizStore {
  availableCount = $state<number>(0); // サイドバー pill 用
  quizzes = $state<QuizListItem[]>([]);
  draftAnswers = $state<Record<string, QuizAnswer>>({});
  saveStatus = $state<"idle" | "saving" | "saved">("idle");
  savedAt = $state<string | null>(null);
  // 途中保存先のセッション文脈（session ページ入室時に setContext で確定）。
  #ctx: { orgSlug: string; projectSlug: string; sessionId: string } | null = null;

  async loadAvailable(orgSlug: string, projectSlug: string) {
    const list = await listQuizzes(orgSlug, projectSlug);
    this.quizzes = list.quizzes;
    this.availableCount = list.quizzes.length;
  }

  setContext(orgSlug: string, projectSlug: string, sessionId: string) {
    this.#ctx = { orgSlug, projectSlug, sessionId };
    this.draftAnswers = {};
    this.saveStatus = "idle";
    this.savedAt = null;
  }

  async saveDraft(answer: QuizAnswer) {
    this.saveStatus = "saving";
    this.draftAnswers = { ...this.draftAnswers, [answer.question_id]: answer };
    this.savedAt = answer.saved_at;
    if (!this.#ctx) {
      this.saveStatus = "saved";
      return;
    }
    try {
      const saved = await saveQuizAnswer(this.#ctx.orgSlug, this.#ctx.projectSlug, this.#ctx.sessionId, answer);
      this.savedAt = saved.saved_at;
      this.saveStatus = "saved";
    } catch {
      this.saveStatus = "idle"; // 保存失敗時はドラフトは保持しつつ未保存に戻す
    }
  }

  reset() {
    this.#ctx = null;
    this.draftAnswers = {};
    this.saveStatus = "idle";
    this.savedAt = null;
  }
}

export const quiz = new QuizStore();
