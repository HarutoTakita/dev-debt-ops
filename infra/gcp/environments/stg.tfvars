project_name = "dev-debt-ops"
environment  = "stg"

# 公開ドメイン（Google マネージド証明書 + OAuth コールバックのオリジン）。
# 初回デプロイ後に LB IP を取得し、この FQDN の A レコードをその IP に向ける。
domain = "stg.devdebtops.harutotakita.dev"

# GitHub App / OAuth の非機密識別子。この環境用に作成した GitHub App の値を入れる。
# 秘密鍵 / client secret は GitHub Actions secrets（GH_APP_PRIVATE_KEY / GH_CLIENT_SECRET）側（ここではない）。
github_app_id    = "4151789"
github_app_slug  = "devdebtops-stg"
github_client_id = "Iv23liHhadKwbVgb8ZlP"

api_cpu           = "1"
api_memory        = "512Mi"
api_min_instances = 0

service_cpu           = "2"
service_memory        = "2Gi"
service_min_instances = 0

db_tier           = "db-f1-micro"
db_disk_size      = 10
db_backup_enabled = false
# staging: Cloud SQL public IP + authorized networks (simplified networking).
