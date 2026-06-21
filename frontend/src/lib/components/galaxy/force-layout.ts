// 依存グラフの決定的フォースレイアウト（Fruchterman–Reingold 簡略版、issue 050）。
// ギャラクシーのマップは従来ノードを固定座標へ index 剰余で割り当てていたため、配置が依存構造を
// 反映せず線が錯綜していた。実依存エッジから力学配置を計算し、つながりを読めるようにする。
//
// 制約: SPA は外部ホストへ通信不可のため自己完結（外部ライブラリ不使用）。Math.random 非依存
// （円周シードで決定的）— 同一入力なら常に同一レイアウトで、再レンダリングでも安定する。

export type Point = { x: number; y: number };

export type ForceLayoutOptions = {
  iterations?: number; // 反復回数
  padding?: number; // 枠からの余白（% 座標）
  gravity?: number; // 中心への引力係数
  initialRadius?: number; // 円周シードの半径
};

/**
 * ノード id 配列と無向エッジ（重複・自己ループは内部で除外）からレイアウトを計算する。
 * 返り値は id → % 座標（[padding, 100 - padding] にクランプ）。ノード数は小規模（モジュール数）
 * を想定し O(n^2 · iterations) で十分。
 */
export function computeForceLayout(
  nodes: string[],
  edges: ReadonlyArray<readonly [string, string]>,
  options: ForceLayoutOptions = {},
): Map<string, Point> {
  const n = nodes.length;
  const result = new Map<string, Point>();
  if (n === 0) return result;

  const padding = options.padding ?? 12;
  const center = 50;
  if (n === 1) {
    result.set(nodes[0], { x: center, y: center });
    return result;
  }

  const iterations = options.iterations ?? 300;
  const gravity = options.gravity ?? 0.02;
  const initialRadius = options.initialRadius ?? 28;
  const span = 100 - 2 * padding;
  const k = Math.sqrt((span * span) / n); // 理想ノード間距離
  const eps = 0.01;

  const index = new Map<string, number>();
  nodes.forEach((id, i) => index.set(id, i));

  // 円周上に決定的に初期配置（index 順）。
  const px: number[] = new Array(n);
  const py: number[] = new Array(n);
  for (let i = 0; i < n; i++) {
    const a = (2 * Math.PI * i) / n;
    px[i] = center + initialRadius * Math.cos(a);
    py[i] = center + initialRadius * Math.sin(a);
  }

  // エッジを index ペアへ正規化（無向で重複排除、自己ループ・未知ノードを除外）。
  const eu: number[] = [];
  const ev: number[] = [];
  const seen = new Set<string>();
  for (const [u, v] of edges) {
    const iu = index.get(u);
    const iv = index.get(v);
    if (iu === undefined || iv === undefined || iu === iv) continue;
    const key = iu < iv ? `${iu}|${iv}` : `${iv}|${iu}`;
    if (seen.has(key)) continue;
    seen.add(key);
    eu.push(iu);
    ev.push(iv);
  }

  const dx: number[] = new Array(n);
  const dy: number[] = new Array(n);
  let temp = span / 10; // 初期温度（1 反復あたりの最大移動量）

  for (let iter = 0; iter < iterations; iter++) {
    for (let i = 0; i < n; i++) {
      dx[i] = 0;
      dy[i] = 0;
    }

    // 反発（全ペア）: 近いほど強く押し離す。
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        let ddx = px[i] - px[j];
        let ddy = py[i] - py[j];
        let dist = Math.hypot(ddx, ddy);
        if (dist < eps) {
          ddx = eps;
          ddy = 0;
          dist = eps;
        }
        const force = (k * k) / dist;
        const fx = (ddx / dist) * force;
        const fy = (ddy / dist) * force;
        dx[i] += fx;
        dy[i] += fy;
        dx[j] -= fx;
        dy[j] -= fy;
      }
    }

    // 引力（エッジ）: 連結ノードをバネで引き寄せる。
    for (let e = 0; e < eu.length; e++) {
      const i = eu[e];
      const j = ev[e];
      let ddx = px[i] - px[j];
      let ddy = py[i] - py[j];
      let dist = Math.hypot(ddx, ddy);
      if (dist < eps) {
        ddx = eps;
        ddy = 0;
        dist = eps;
      }
      const force = (dist * dist) / k;
      const fx = (ddx / dist) * force;
      const fy = (ddy / dist) * force;
      dx[i] -= fx;
      dy[i] -= fy;
      dx[j] += fx;
      dy[j] += fy;
    }

    // 中心への重力 + 温度で移動量を制限（冷却）。
    for (let i = 0; i < n; i++) {
      dx[i] += (center - px[i]) * gravity;
      dy[i] += (center - py[i]) * gravity;
      const dl = Math.hypot(dx[i], dy[i]);
      if (dl > eps) {
        px[i] += (dx[i] / dl) * Math.min(dl, temp);
        py[i] += (dy[i] / dl) * Math.min(dl, temp);
      }
    }
    temp *= 0.97;
  }

  for (let i = 0; i < n; i++) {
    result.set(nodes[i], {
      x: Math.max(padding, Math.min(100 - padding, px[i])),
      y: Math.max(padding, Math.min(100 - padding, py[i])),
    });
  }
  return result;
}
