# Two Cloud Run services (issue-015): `api` (external, behind the HTTPS LB) and `service`
# (internal-only worker, invoked by Cloud Tasks). Both connect to Cloud SQL — api owns
# migrations + queries + the GET /jobs/{id} poll response; service writes Job results.
#
# Plaintext env keys are 1:1 with issue-016's Settings (canonical names live in 016).
# USE_MOCK_* are forced false so prod uses real Cloud Tasks / GCS (the app defaults are
# mock=true for local dev — they MUST be overridden here or api would never dispatch).
locals {
  api_plain_env = {
    ENVIRONMENT           = var.environment
    COOKIE_SECURE         = "true"
    GOOGLE_CLOUD_PROJECT  = var.gcp_project_id
    GOOGLE_CLOUD_LOCATION = var.region
    TASKS_QUEUE           = var.tasks_queue
    TASKS_INVOKER_SA      = google_service_account.tasks_invoker.email
    JOB_PAYLOAD_BUCKET    = google_storage_bucket.job_payloads.name
    SERVICE_TASKS_URL     = google_cloud_run_v2_service.service.uri
    USE_MOCK_QUEUE        = "false"
    USE_MOCK_WORKER       = "false"
    USE_MOCK_BLOB         = "false"
  }

  api_secret_env = {
    SECRET_KEY             = "secret-key"
    GITHUB_APP_PRIVATE_KEY = "github-app-private-key"
    GITHUB_CLIENT_SECRET   = "github-client-secret"
    GITHUB_WEBHOOK_SECRET  = "github-webhook-secret"
    DATABASE_URL           = "database-url"
  }

  # service does not get SERVICE_TASKS_URL from its own .uri (that would be a cycle). The
  # deploy workflow sets the service's OIDC audience post-create (or via custom_audiences);
  # TASKS_INVOKER_SA lets it check the token principal.
  service_plain_env = {
    ENVIRONMENT           = var.environment
    GOOGLE_CLOUD_PROJECT  = var.gcp_project_id
    GOOGLE_CLOUD_LOCATION = var.region
    JOB_PAYLOAD_BUCKET    = google_storage_bucket.job_payloads.name
    TASKS_INVOKER_SA      = google_service_account.tasks_invoker.email
    USE_MOCK_QUEUE        = "false"
  }

  service_secret_env = {
    DATABASE_URL = "database-url"
  }
}

resource "google_cloud_run_v2_service" "api" {
  name     = "${local.name_prefix}-api"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"

  deletion_protection = var.environment == "prod"

  template {
    service_account = google_service_account.api.email
    timeout         = var.api_timeout

    scaling {
      min_instance_count = var.api_min_instances
      max_instance_count = var.api_max_instances
    }

    vpc_access {
      connector = google_vpc_access_connector.main.id
      egress    = "PRIVATE_RANGES_ONLY"
    }

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.main.connection_name]
      }
    }

    containers {
      image = var.container_image_api

      resources {
        limits = {
          cpu    = var.api_cpu
          memory = var.api_memory
        }
      }

      ports {
        container_port = 8000
      }

      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }

      dynamic "env" {
        for_each = local.api_plain_env
        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = local.api_secret_env
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.secrets[env.value].secret_id
              version = "latest"
            }
          }
        }
      }
    }
  }

  depends_on = [google_secret_manager_secret_iam_member.accessors]
}

resource "google_cloud_run_v2_service" "service" {
  name     = "${local.name_prefix}-service"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_ONLY"

  deletion_protection = var.environment == "prod"

  template {
    service_account = google_service_account.service.email
    timeout         = var.service_timeout

    scaling {
      min_instance_count = var.service_min_instances
      max_instance_count = var.service_max_instances
    }

    vpc_access {
      connector = google_vpc_access_connector.main.id
      egress    = "PRIVATE_RANGES_ONLY"
    }

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.main.connection_name]
      }
    }

    containers {
      image = var.container_image_service

      resources {
        limits = {
          cpu    = var.service_cpu
          memory = var.service_memory
        }
      }

      ports {
        container_port = 8000
      }

      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }

      dynamic "env" {
        for_each = local.service_plain_env
        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = local.service_secret_env
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.secrets[env.value].secret_id
              version = "latest"
            }
          }
        }
      }
    }
  }

  depends_on = [google_secret_manager_secret_iam_member.accessors]
}

# Only the Cloud Tasks invoker SA may call service (OIDC). Never allUsers — external reach
# is the LB-fronted api only.
resource "google_cloud_run_v2_service_iam_member" "service_tasks_invoker" {
  name     = google_cloud_run_v2_service.service.name
  location = google_cloud_run_v2_service.service.location
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.tasks_invoker.email}"
}
