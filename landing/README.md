# Landing page (LP)

アプリとは別に公開する静的ランディングページ。単一の `index.html`（Tailwind CDN）で完結し、
**アプリ（Cloud Run）とは独立にデプロイ**する。

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

アプリのビルド/デプロイとは独立。バケットへ静的ファイルを同期するだけ：

```bash
BUCKET=$(terraform -chdir=infra/gcp output -raw landing_bucket)   # 空ならまだ lp_domain 未設定
APP_URL="https://app.example.com"

# アプリ導線の差し込み（CTA の href）。
sed "s|APP_URL_PLACEHOLDER|${APP_URL}|g" landing/index.html > /tmp/index.html

gcloud storage cp /tmp/index.html "gs://${BUCKET}/index.html" \
  --cache-control="public, max-age=300"
```

CI に組み込む場合は、デプロイワークフローの末尾にこの同期ステップ（`landing_bucket` が空でない時のみ実行）を追加する。

## アプリ側のリンク

サイドバーのヘルプ「LP を確認する」は、フロントのビルド時 env `VITE_LP_URL`（`frontend/.env`）に
LP の URL を設定すると有効化され、別タブで開く。未設定時は無効のまま。
