# Landing page (LP)

アプリとは別に公開する静的ランディングページ。**アプリ（Cloud Run）とは独立にデプロイ**する。

Tailwind は本番非推奨の Play CDN（`cdn.tailwindcss.com`）を使わず、**ビルド時にコンパイルして同梱**する。
配信物は `index.html` ＋ `styles.css` ＋ `og-image.png` の 3 ファイル（いずれもリポジトリにコミット済み）。

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
