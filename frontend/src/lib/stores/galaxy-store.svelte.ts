import { getCodeGraph, getGalaxy } from "$lib/api/client";
import type { PersonalGalaxy } from "$lib/api/schemas";
import { mockGalaxy } from "$lib/mocks/galaxy";

class GalaxyStore {
  galaxy = $state<PersonalGalaxy | null>(null);
  // CodeGraphContext の file↔file 結合エッジ（issue 238）。Level-2 のファイルグラフのエッジに使う。
  // 未構築/取得失敗時は空＝star-map が従来の wormhole にフォールバック。
  codeGraphEdges = $state<{ source: string; target: string }[]>([]);

  // 星域が観測済みか（未観測なら ComingSoonPlaceholder を表示）
  get observed(): boolean {
    return this.galaxy?.observed ?? false;
  }

  // サイドバー pill 用: 自分の KC%（0–100 整数）。未観測時は null。
  myKc = $derived(this.galaxy ? Math.round(this.galaxy.org_kc * 100) : null);

  // 実 API（issue 032）: 最新 kc_analysis run を投影して取得。未観測（observed=false）でも代入する。
  // あわせて code-graph（issue 238）も取得（失敗しても galaxy 表示は止めない＝従来エッジにフォールバック）。
  async load(orgSlug: string, projectSlug: string) {
    const [galaxy, codeGraph] = await Promise.all([
      getGalaxy(orgSlug, projectSlug),
      getCodeGraph(orgSlug, projectSlug).catch(() => null),
    ]);
    this.galaxy = galaxy;
    this.codeGraphEdges = codeGraph?.observed ? codeGraph.file_edges : [];
  }

  // デモ: モックを読み込む（ComingSoonPlaceholder の「デモを見る」用）。
  loadMock() {
    this.galaxy = { ...mockGalaxy, observed: true };
    this.codeGraphEdges = [];
  }

  reset() {
    this.galaxy = null;
    this.codeGraphEdges = [];
  }
}

export const galaxy = new GalaxyStore();
