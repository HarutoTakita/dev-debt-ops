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

  // MVP: モックを読み込む。本実装ではここを実 API（後続 issue）に差し替える。
  loadMock() {
    this.galaxy = { ...mockGalaxy, observed: true };
  }

  reset() {
    this.galaxy = null;
  }
}

export const galaxy = new GalaxyStore();
