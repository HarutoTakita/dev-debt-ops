# Landing page (LP)

静的ランディングページ。Tailwind は本番非推奨の Play CDN（`cdn.tailwindcss.com`）を使わず、**ビルド時に
コンパイルして同梱**する。配信物は `index.html` ＋ `styles.css` ＋ `og-image.png`（いずれもコミット済み）。

## 配信（現行・既定）: アプリと同一ドメインの `/lp`

ハッカソン用途のため、別ドメイン/別バケットは使わず **アプリと同じドメインの `/lp`** で配信する（issue: LP 公開）。

- `docker/api.Dockerfile`（frontend ステージ）が `landing/index.html` / `styles.css` / `og-image.png` / `assets`
  を SPA ビルド出力の `build/lp/` に同梱し、runtime で `app/static/lp/` になる。
- `backend/api/app/main.py` が SPA キャッチオール（`/`）より先に `/lp` を静的マウント（`html=True`）→ `/lp`・`/lp/`
  とも `index.html` を返す。**追加の GCS バケット・サブドメイン・証明書・DNS・CI ステップは不要**（api の既存
  デプロイに同梱される）。
- アプリからの入口: ルート `/`（未ログイン）の「サービスを詳しく見る」とサイドバーのヘルプ「LP を確認する」。
  どちらもビルド時 env **`VITE_LP_URL`**（Docker では `/lp` を注入）で有効化。dev では未設定＝リンク非表示、
  かつ vite は `/lp` を配信しないため LP は prod/stg（api 配信）で確認する。
- `styles.css` はコミット済みのため Docker では再ビルド不要。クラス/OGP を変えたら下記「ビルド」を流して
  `styles.css` を更新・コミットする。

## ビルド

クラスや OGP 画像を変更したら再ビルドする（Node 必須）。

```bash
cd landing
npm install        # 初回のみ（@tailwindcss/cli, sharp）
npm run build      # styles.css（Tailwind）＋ og-image.png を生成
# 個別: npm run build:css / npm run build:og / npm run watch:css
```

- `input.css` — Tailwind 入力。ブランドトークン（`know`/`code`/`ink`・Inter）を `@theme` で定義。
- `assets/og-image.svg` — OGP 画像のソース（`sharp` で 1200×630 PNG へラスタライズ）。

## ホスティング構成（Option A: 同一 LB ＋ バックエンドバケット）

`infra/gcp` の Terraform に組み込み済み。`var.lp_domain` を設定すると、

- `*-{env}-landing` という GCS バケット（静的・公開読み取り）
- Cloud CDN 付きバックエンドバケット
- 既存の外部 HTTPS LB に **ホストルーティング**（`var.lp_domain` → LP バケット、それ以外 → アプリ）
- マネージド証明書に `var.lp_domain` を追加（アプリドメインと同一証明書）

が作成される（`var.lp_domain` 未設定なら一切作られず `plan` は通る）。

```hcl
# infra/gcp/environments/<env>.tfvars
domain    = "app.example.com"   # アプリ
lp_domain = "example.com"       # LP（apex などお好みのホスト）
```

DNS: `terraform output lb_ip` の IP に、`lp_domain` の A レコードを向ける（アプリと同じ LB IP）。

## デプロイ（LP のアップロード）

アプリのビルド/デプロイとは独立。`npm run build` 済みの静的ファイルをバケットへ同期する：

```bash
BUCKET=$(terraform -chdir=infra/gcp output -raw landing_bucket)   # 空ならまだ lp_domain 未設定
APP_URL="https://app.example.com"

# アプリ導線の差し込み（CTA の href）。
sed "s|APP_URL_PLACEHOLDER|${APP_URL}|g" landing/index.html > /tmp/index.html

gcloud storage cp /tmp/index.html "gs://${BUCKET}/index.html" \
  --cache-control="public, max-age=300"
gcloud storage cp landing/styles.css landing/og-image.png "gs://${BUCKET}/" \
  --cache-control="public, max-age=86400"
```

CI に組み込む場合は、デプロイワークフローの末尾にこの同期ステップ（`landing_bucket` が空でない時のみ実行）を追加する。
`styles.css` / `og-image.png` はコミット済みなので、CI でビルドを省略してもそのまま同期できる（変更時は `npm run build` を流す）。

## アプリ側のリンク

サイドバーのヘルプ「LP を確認する」は、フロントのビルド時 env `VITE_LP_URL`（`frontend/.env`）に
LP の URL を設定すると有効化され、別タブで開く。未設定時は無効のまま。
