# Cloud SQL PostgreSQL 17. Both Cloud Run services connect to it (api owns migrations +
# queries; service writes Job results). pgvector is available on PG17 and is enabled by the
# Alembic migration via `CREATE EXTENSION vector` (no instance flag required).
#
# prod: private IP only (reached via the Serverless VPC connector + private service access).
# staging: public IP + authorized networks (simplified, mirrors azure/aws staging).
resource "google_sql_database_instance" "main" {
  name             = "${local.name_prefix}-pg"
  database_version = "POSTGRES_17"
  region           = var.region

  deletion_protection = var.environment == "prod"

  settings {
    tier = var.db_tier
    # ENTERPRISE edition allows shared-core (db-f1-micro, stg) and custom (db-custom-*, prod)
    # tiers. The API now defaults new instances to ENTERPRISE_PLUS, which rejects db-f1-micro.
    edition           = "ENTERPRISE"
    disk_size         = var.db_disk_size
    disk_autoresize   = true
    availability_type = var.environment == "prod" ? "REGIONAL" : "ZONAL"

    backup_configuration {
      enabled = var.db_backup_enabled
    }

    ip_configuration {
      ipv4_enabled    = var.environment != "prod"
      private_network = var.environment == "prod" ? google_compute_network.main.id : null

      dynamic "authorized_networks" {
        # Staging only: open to all (paired with TLS). prod has no public IP.
        for_each = var.environment == "prod" ? [] : [1]
        content {
          name  = "all"
          value = "0.0.0.0/0"
        }
      }
    }
  }

  depends_on = [
    google_project_service.services,
    google_service_networking_connection.private_vpc,
  ]
}

resource "google_sql_database" "main" {
  name     = local.db_name
  instance = google_sql_database_instance.main.name
}

resource "google_sql_user" "main" {
  name     = var.db_username
  instance = google_sql_database_instance.main.name
  password = var.db_password
}
