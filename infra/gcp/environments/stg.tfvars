environment = "stg"

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
