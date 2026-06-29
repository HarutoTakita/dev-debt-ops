import { type Page } from "@playwright/test";
import path from "node:path";
import fs from "node:fs";
import { fileURLToPath } from "node:url";

/**
 * DevDebtOps の画面スクリーンショット取得ヘルパー（仕様書兼取扱説明書の自動生成ベース）。
 *
 * 認証は GitHub OAuth ではなく **ゲストデモログイン**（issue 069, `POST /api/v1/auth/demo`）を使う。
 * これにより GitHub なしでシード済みデモ org（`demo` / `sample-shop`）の全画面を撮影できる。
 * 前提条件は screenshots/README.md を参照（バックエンドの DEMO_MODE_ENABLED=true + seed_demo）。
 */

// このファイル（frontend/screenshots/）からリポジトリルートは ../../。cwd に依存せず解決する。
const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(HERE, "../../");
const SHOT_ROOT = path.resolve(REPO_ROOT, "docs/取扱説明書/images/screens");
const MANIFEST = path.resolve(REPO_ROOT, "docs/取扱説明書/screens.manifest.json");

// シード済みデモワークスペース（backend/api/app/scripts/seed_demo.py と一致させること）。
export const ORG = "demo";
export const PROJECT = "sample-shop";
export const BASE = `/${ORG}/${PROJECT}`;

type ShotMeta = { title: string; route: string; file: string; capturedAt: string };

/** manifest.json に1ページ分のメタ情報を upsert する（key で冪等。仕様書生成の入力になる）。 */
function upsertManifest(key: string, entry: Omit<ShotMeta, "capturedAt">): void {
  let manifest: Record<string, ShotMeta>;
  try {
    manifest = JSON.parse(fs.readFileSync(MANIFEST, "utf-8"));
  } catch {
    manifest = {};
  }
  manifest[key] = { ...entry, capturedAt: new Date().toISOString() };
  // キー（= 表示順の番号プレフィックス）でソートして安定出力。
  const sorted = Object.fromEntries(Object.entries(manifest).sort(([a], [b]) => a.localeCompare(b)));
  fs.mkdirSync(path.dirname(MANIFEST), { recursive: true });
  fs.writeFileSync(MANIFEST, JSON.stringify(sorted, null, 2) + "\n");
}

/**
 * 安定状態まで待ってから `<key>.png` を撮影し、manifest にメタを記録する。
 * `key` は表示順の番号プレフィックス付きにする（例: "03-overview"）。
 */
export async function shot(
  page: Page,
  key: string,
  opts: { title: string; route?: string; fit?: boolean } = { title: "" },
): Promise<string> {
  fs.mkdirSync(SHOT_ROOT, { recursive: true });
  const file = path.join(SHOT_ROOT, `${key}.png`);

  // ネットワーク・ローディング表示・スピナーが落ち着くまで待つ。
  await page.waitForLoadState("networkidle").catch(() => {});
  await page
    .locator("text=読み込み中")
    .first()
    .waitFor({ state: "hidden", timeout: 15_000 })
    .catch(() => {});
  await page
    .locator(".animate-spin")
    .first()
    .waitFor({ state: "hidden", timeout: 15_000 })
    .catch(() => {});

  // 取扱説明書用の画像には「デモ環境です」バナー（issue 069, [org]/+layout）は不要なので、
  // デモ認証は維持したまま撮影直前にそのバナー要素だけ DOM から除去する。
  await page
    .evaluate(() => {
      for (const el of document.querySelectorAll('[role="status"]')) {
        if (el.textContent?.includes("デモ環境")) el.remove();
      }
    })
    .catch(() => {});

  // 画像は常に固定アスペクト比（= ビューポート 1440x900）で撮る。このアプリは h-screen シェル内で <main> だけが
  // 内部スクロールするため、単に zoom してもシェルが縮むだけでクリップは解けない。そこで fit 時は
  // (1) 内部スクロールを一旦解除してページ全体を自然な高さに流し、(2) 全高に合わせて zoom で 1 画面に収める。
  // ただし長いリスト（コード品質マップ等）は無理に収めない: zoom が下限(0.7)を下回るほど縦長なら
  // 解除・zoom せず、ビューポート上部をそのまま撮る。
  const MIN_ZOOM = 0.7;
  let adjusted = false;
  if (opts.fit) {
    const viewport = page.viewportSize();
    // 内部スクロールを解除して全コンテンツ高を測る（解除した要素には data-shot-unlocked を付け、後で復元）。
    const fullHeight = await page
      .evaluate(() => {
        const main = document.querySelector("main");
        if (!main) return 0;
        const touch = (el: HTMLElement) => {
          el.dataset.shotUnlocked = "1";
          el.style.overflow = "visible";
          el.style.height = "auto";
          el.style.minHeight = "0";
        };
        touch(main as HTMLElement);
        let el = main.parentElement;
        while (el && el !== document.body) {
          touch(el);
          el = el.parentElement;
        }
        return Math.ceil(document.documentElement.scrollHeight);
      })
      .catch(() => 0);

    const restore = () =>
      page.evaluate(() => {
        document.documentElement.style.removeProperty("zoom");
        for (const el of document.querySelectorAll<HTMLElement>("[data-shot-unlocked]")) {
          el.style.removeProperty("overflow");
          el.style.removeProperty("height");
          el.style.removeProperty("min-height");
          delete el.dataset.shotUnlocked;
        }
      });

    if (viewport && fullHeight > viewport.height) {
      const zoom = (viewport.height - 16) / fullHeight; // 下端に少し余白
      if (zoom >= MIN_ZOOM) {
        await page.evaluate((z) => document.documentElement.style.setProperty("zoom", String(z)), zoom);
        await page.evaluate(() => window.scrollTo(0, 0));
        await page.waitForTimeout(300); // zoom 後のレイアウト/チャート再描画を待つ
        adjusted = true;
      } else {
        await restore(); // 収まらない長いページは解除を戻し、ビューポート上部をそのまま撮る
      }
    } else {
      await restore(); // もともと収まるページは変更不要
    }
  }

  // 常にビューポート撮影（固定アスペクト比）。fit 時は解除 + zoom で全体を 1 画面に収めている。
  await page.screenshot({ path: file, animations: "disabled" });

  if (adjusted) {
    await page.evaluate(() => {
      document.documentElement.style.removeProperty("zoom");
      for (const el of document.querySelectorAll<HTMLElement>("[data-shot-unlocked]")) {
        el.style.removeProperty("overflow");
        el.style.removeProperty("height");
        el.style.removeProperty("min-height");
        delete el.dataset.shotUnlocked;
      }
    });
  }
  upsertManifest(key, {
    title: opts.title || key,
    route: opts.route ?? new URL(page.url()).pathname,
    file: path.relative(REPO_ROOT, file),
  });
  return file;
}

/**
 * ゲストデモにログインし、デモ org のダッシュボードまで遷移する。
 * 併せてログイン画面（"01-login"）も撮影する。
 *
 * 通常は「お試しはこちら」ボタンを押す（DEMO_MODE_ENABLED 時のみ表示）。
 * ボタンが出ない場合は `POST /api/v1/auth/demo` に直接フォールバックする
 * （cookie はページコンテキストと共有されるため、その後の遷移でログイン状態になる）。
 */
export async function startDemo(page: Page): Promise<void> {
  await page.goto("/login");
  await shot(page, "01-login", { title: "ログイン / お試しデモ入口", route: "/login" });

  const demoBtn = page.getByRole("button", { name: "お試しはこちら" });
  try {
    await demoBtn.waitFor({ state: "visible", timeout: 5_000 });
    await demoBtn.click();
  } catch {
    const res = await page.request.post("/api/v1/auth/demo");
    if (!res.ok()) {
      throw new Error(
        "デモログインに失敗しました。バックエンドで DEMO_MODE_ENABLED=true を設定し、seed_demo を実行してください（screenshots/README.md 参照）。",
      );
    }
    await page.goto(`/${ORG}`);
  }

  await page.waitForURL(`**/${ORG}**`, { timeout: 15_000 }).catch(() => {});
  await applyProjectSections(page);
  await page.waitForLoadState("networkidle").catch(() => {});
}

/**
 * サイドバーのプロジェクト整理（スター付き + ユーザー定義セクション）を全画面に適用する。
 * これらはクライアント側 localStorage（key "rosetta:project-sections"）に保持されるため、デモ org の
 * プロジェクト id を解決して状態を流し込む。次回以降の page.goto（リロード）で store が読み直してグループ表示になる。
 * 複数プロジェクトは seed_demo.py の _EXTRA_PROJECTS で投入済み。best-effort（失敗してもフラット表示で撮影継続）。
 */
async function applyProjectSections(page: Page): Promise<void> {
  try {
    const res = await page.request.get(`/api/v1/orgs/${ORG}/projects`);
    const data = (await res.json()) as { projects?: { id: string; slug: string }[] };
    const idOf: Record<string, string> = {};
    for (const p of data.projects ?? []) idOf[p.slug] = p.id;
    const assign = (slug: string, section: string): [string, string][] => (idOf[slug] ? [[idOf[slug], section]] : []);
    const state = {
      [ORG]: {
        starred: idOf["sample-shop"] ? [idOf["sample-shop"]] : [],
        sections: [
          { id: "sec-core", name: "コアサービス", color: 0 },
          { id: "sec-frontend", name: "フロントエンド", color: 3 },
        ],
        assignments: Object.fromEntries([
          ...assign("billing-service", "sec-core"),
          ...assign("inventory-api", "sec-core"),
          ...assign("marketing-site", "sec-frontend"),
          ...assign("mobile-app", "sec-frontend"),
        ]),
        collapsed: [],
      },
    };
    await page.evaluate((s) => localStorage.setItem("rosetta:project-sections", JSON.stringify(s)), state);
  } catch {
    // best-effort: グループ未設定（フラット表示）でも撮影は続行する。
  }
}
