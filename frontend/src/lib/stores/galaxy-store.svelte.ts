import { getGalaxy } from "$lib/api/client";
import type { PersonalGalaxy } from "$lib/api/schemas";
import { mockGalaxy } from "$lib/mocks/galaxy";

class GalaxyStore {
  galaxy = $state<PersonalGalaxy | null>(null);

  // 星域が観測済みか（未観測なら ComingSoonPlaceholder を表示）
  get observed(): boolean {
    return this.galaxy?.observed ?? false;
  }

  // サイドバー pill 用: 自分の KC%（0–100 整数）。未観測時は null。
  myKc = $derived(this.galaxy ? Math.round(this.galaxy.org_kc * 100) : null);

  // 実 API（issue 032）: 最新 kc_analysis run を投影して取得。未観測（observed=false）でも代入する。
  async load(orgSlug: string, projectSlug: string) {
    this.galaxy = await getGalaxy(orgSlug, projectSlug);
  }

  // デモ: モックを読み込む（ComingSoonPlaceholder の「デモを見る」用）。
  loadMock() {
    this.galaxy = { ...mockGalaxy, observed: true };
  }

  reset() {
    this.galaxy = null;
  }
}

export const galaxy = new GalaxyStore();
