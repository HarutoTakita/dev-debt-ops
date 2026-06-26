project_name = "dev-debt-ops"
environment  = "prod"

# 公開ドメイン（Google マネージド証明書 + OAuth コールバックのオリジン）。
domain = "devdebtops.harutotakita.dev"

# GitHub App / OAuth の非機密識別子。本番用に作成した GitHub App の値を入れる。
# 秘密鍵 / client secret は GitHub Actions secrets 側（ここではない）。
# github_app_id    = "<numeric app id>"
# github_app_slug  = "<app slug>"
# github_client_id = "<Iv23... client id>"

api_cpu           = "2"
api_memory        = "1Gi"
api_min_instances = 1

service_cpu           = "4"
service_memory        = "4Gi"
service_min_instances = 0

db_tier           = "db-custom-2-7680"
db_disk_size      = 50
db_backup_enabled = true
# prod: Cloud SQL private IP + VPC connector, deletion_protection = true.
