import { listQuizzes, saveQuizAnswer, setQuestionFlag } from "$lib/api/client";
import type { QuizAnswer, QuizListItem } from "$lib/api/schemas";

// クイズ返済体験のストア（Svelte 5 クラスベース runes）。
// 一覧取得と途中保存（PATCH upsert）を実 API で配線（issue 034）。採点は result ローダで実行。
class QuizStore {
  availableCount = $state<number>(0); // サイドバー pill 用
  quizzes = $state<QuizListItem[]>([]);
  draftAnswers = $state<Record<string, QuizAnswer>>({});
  saveStatus = $state<"idle" | "saving" | "saved" | "error">("idle");
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
      // コンテキスト未設定では保存できない → 「保存済み」と偽らずエラーにする（通常は到達しない防御的分岐）。
      console.error("quiz saveDraft: session context not set; answer was not persisted");
      this.saveStatus = "error";
      return;
    }
    try {
      const saved = await saveQuizAnswer(this.#ctx.orgSlug, this.#ctx.projectSlug, this.#ctx.sessionId, answer);
      this.savedAt = saved.saved_at;
      this.saveStatus = "saved";
    } catch {
      // 保存失敗（採点済みの 409・ネットワーク等）はドラフトを保持しつつ明示的にエラー表示する
      // （黙って「未保存」に戻すと、保存できていないことにユーザーが気づけない）。
      this.saveStatus = "error";
    }
  }

  // 設問フラグの永続化（#6）。ローカル状態は focus-mode が保持し、ここは PUT のみ担う。
  async flagQuestion(questionId: string, flagged: boolean) {
    if (!this.#ctx) return;
    await setQuestionFlag(this.#ctx.orgSlug, this.#ctx.projectSlug, this.#ctx.sessionId, questionId, flagged);
  }

  reset() {
    this.#ctx = null;
    this.draftAnswers = {};
    this.saveStatus = "idle";
    this.savedAt = null;
  }
}

export const quiz = new QuizStore();
