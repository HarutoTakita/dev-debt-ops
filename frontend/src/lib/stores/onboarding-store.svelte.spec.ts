import { describe, it, expect } from "vitest";
import { OnboardingStore } from "./onboarding-store.svelte";

// 初回プロジェクト作成 → 自動開始（ワンショット）/ 完了の永続 / ステップ進行（issue 066）。
describe("OnboardingStore", () => {
  it("auto-start is a one-shot per org", () => {
    const s = new OnboardingStore();
    s.requestAutoStart("acme");
    expect(s.consumeAutoStart("acme")).toBe(true); // 初回だけ true
    expect(s.consumeAutoStart("acme")).toBe(false); // 消費済み
  });

  it("does not auto-start for a different org", () => {
    const s = new OnboardingStore();
    s.requestAutoStart("acme");
    expect(s.consumeAutoStart("other")).toBe(false);
  });

  it("does not auto-start once completed", () => {
    const s = new OnboardingStore();
    s.finish("acme"); // 完了フラグ
    s.requestAutoStart("acme");
    expect(s.consumeAutoStart("acme")).toBe(false);
    expect(s.isCompleted("acme")).toBe(true);
  });

  it("start / next / prev / finish drive active + step", () => {
    const s = new OnboardingStore();
    s.start([
      { id: "a", title: () => "a", body: () => "a", placement: "right" },
      { id: "b", title: () => "b", body: () => "b", placement: "right" },
    ]);
    expect(s.active).toBe(true);
    expect(s.stepIndex).toBe(0);
    s.next();
    expect(s.stepIndex).toBe(1);
    s.prev();
    expect(s.stepIndex).toBe(0);
    s.prev(); // 0 でクランプ
    expect(s.stepIndex).toBe(0);
    s.finish("acme");
    expect(s.active).toBe(false);
    expect(s.stepIndex).toBe(0);
    expect(s.isCompleted("acme")).toBe(true);
  });
});
