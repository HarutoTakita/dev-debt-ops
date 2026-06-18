import { getQuizSession, listQuizzes } from "$lib/api/client";
import type { QuizAnswer, QuizListItem, QuizSession } from "$lib/api/schemas";

// クイズ返済体験のストア（Svelte 5 クラスベース runes）。
// 受験ロジック・採点本体は未実装（後続 issue）。ここはモック配線 + 途中保存ドラフトのみ。
class QuizStore {
  availableCount = $state<number>(0); // サイドバー pill 用
  quizzes = $state<QuizListItem[]>([]);
  current = $state<QuizSession | null>(null);
  draftAnswers = $state<Record<string, QuizAnswer>>({});
  saveStatus = $state<"idle" | "saving" | "saved">("idle");
  savedAt = $state<string | null>(null);

  async loadAvailable(orgSlug: string) {
    const list = await listQuizzes(orgSlug);
    this.quizzes = list.quizzes;
    this.availableCount = list.quizzes.length;
  }

  async start(sessionId: string) {
    this.current = await getQuizSession(sessionId);
    this.draftAnswers = {};
    this.saveStatus = "idle";
    this.savedAt = null;
  }

  saveDraft(answer: QuizAnswer) {
    this.saveStatus = "saving";
    this.draftAnswers = { ...this.draftAnswers, [answer.question_id]: answer };
    this.savedAt = answer.saved_at;
    // TODO: 実 API は後続 issue。今は楽観的に保存済みへ。
    this.saveStatus = "saved";
  }

  reset() {
    this.current = null;
    this.draftAnswers = {};
    this.saveStatus = "idle";
    this.savedAt = null;
  }
}

export const quiz = new QuizStore();
