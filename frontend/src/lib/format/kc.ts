// 理解度（Knowledge Coverage, 0..1 の比率）の数値表記を全画面で統一する。
// 「1 コンセプト 1 エンコーディング」: 同じ書式（四捨五入・小数 0 桁・パーセント）で表示する。
import * as m from "$lib/paraglide/messages";

/** 0..1 の比率を接頭辞なしパーセントへ。例: 0.62 -> "62%" */
export function formatKcPct(value: number): string {
  return `${Math.round(value * 100)}%`;
}

/** 0..1 の比率を「理解度」ラベル付きパーセントへ。例: 0.62 -> "理解度 62%"（ロケール対応）。 */
export function formatKc(value: number): string {
  return `${m.kc_label()} ${formatKcPct(value)}`;
}
