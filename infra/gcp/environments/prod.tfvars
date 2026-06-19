environment = "prod"

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
