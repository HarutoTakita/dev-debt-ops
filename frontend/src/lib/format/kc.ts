// KC（Knowledge Coverage = チーム理解度, 0..1 の比率）の数値表記を全画面で統一する。
// 「1 コンセプト 1 エンコーディング」: KC はどこでも同じ書式（四捨五入・小数 0 桁・パーセント）で表示する。

/** 0..1 の比率を接頭辞なしパーセントへ。例: 0.62 -> "62%" */
export function formatKcPct(value: number): string {
  return `${Math.round(value * 100)}%`;
}

/** 0..1 の比率を "KC " 接頭辞付きパーセントへ。例: 0.62 -> "KC 62%" */
export function formatKc(value: number): string {
  return `KC ${formatKcPct(value)}`;
}
