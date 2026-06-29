// OGP 画像のラスタライズ: assets/og-image.svg → og-image.png（1200×630）。
// SNS クローラの多くが SVG を og:image として描画しないため、PNG を生成して同梱する。
// 日本語グリフはシステムの CJK フォント（Noto Sans CJK JP 等）にフォールバックして描画される。
import { readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import sharp from "sharp";

const here = dirname(fileURLToPath(import.meta.url));
const src = resolve(here, "../assets/og-image.svg");
const out = resolve(here, "../og-image.png");

const svg = await readFile(src);
await sharp(svg, { density: 144 }).resize(1200, 630).png({ compressionLevel: 9 }).toFile(out);

console.log(`og-image.png を生成しました (${out})`);
