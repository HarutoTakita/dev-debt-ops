# Two Cloud Run services (issue-015): `api` (external, behind the HTTPS LB) and `service`
# (internal-only worker, invoked by Cloud Tasks). Both connect to Cloud SQL — api owns
# migrations + queries + the GET /jobs/{id} poll response; service writes Job results.
#
# Plaintext env keys are 1:1 with issue-016's Settings (canonical names live in 016).
# USE_MOCK_* are forced false so prod uses real Cloud Tasks / GCS (the app defaults are
# mock=true for local dev — they MUST be overridden here or api would never dispatch).
locals {
  # Stable OIDC audience for Cloud Tasks → service. Decoupled from the service's run.app URL
  # (which can't be self-referenced in Terraform); the service accepts it via custom_audiences,
  # and its app-level verify_oidc expects it via SERVICE_TASKS_URL.
  service_oidc_audience = "https://${local.name_prefix}-service"

  api_plain_env = {
    ENVIRONMENT              = var.environment
    COOKIE_SECURE            = "true"
    GOOGLE_CLOUD_PROJECT     = var.gcp_project_id
    GOOGLE_CLOUD_LOCATION    = var.region
    TASKS_QUEUE              = var.tasks_queue
    TASKS_INVOKER_SA         = google_service_account.tasks_invoker.email
    JOB_PAYLOAD_BUCKET       = google_storage_bucket.job_payloads.name
    SERVICE_TASKS_URL        = google_cloud_run_v2_service.service.uri
    USE_MOCK_QUEUE           = "false"
    USE_MOCK_WORKER          = "false"
    USE_MOCK_BLOB            = "false"
    GITHUB_APP_ID            = var.github_app_id
    GITHUB_APP_SLUG          = var.github_app_slug
    GITHUB_CLIENT_ID         = var.github_client_id
    FRONTEND_ORIGIN          = var.domain != "" ? "https://${var.domain}" : "http://localhost:5173"
    SERVICE_OIDC_AUDIENCE    = local.service_oidc_audience
    ANALYSIS_CREDITS_ENABLED = tostring(var.analysis_credits_enabled)
    ADMIN_EMAILS             = var.admin_emails
  }

  api_secret_env = {
    SECRET_KEY             = "secret-key"
    GITHUB_APP_PRIVATE_KEY = "github-app-private-key"
    GITHUB_CLIENT_SECRET   = "github-client-secret"
    GITHUB_WEBHOOK_SECRET  = "github-webhook-secret"
    DATABASE_URL           = "database-url"
  }

  # service can't reference its own run.app .uri in Terraform (self-cycle), so SERVICE_TASKS_URL
  # here is the stable OIDC audience (accepted via the service's custom_audiences, and the api
  # mints tokens with the same value). TASKS_INVOKER_SA lets verify_oidc check the token principal.
  service_plain_env = {
    ENVIRONMENT           = var.environment
    GOOGLE_CLOUD_PROJECT  = var.gcp_project_id
    GOOGLE_CLOUD_LOCATION = var.region
    JOB_PAYLOAD_BUCKET    = google_storage_bucket.job_payloads.name
    TASKS_INVOKER_SA      = google_service_account.tasks_invoker.email
    # verify_oidc expects this exact audience; the api mints the OIDC token with the same
    # stable value (SERVICE_OIDC_AUDIENCE) and the service accepts it via custom_audiences.
    SERVICE_TASKS_URL = local.service_oidc_audience
    USE_MOCK_QUEUE    = "false"
    GITHUB_APP_ID     = var.github_app_id
    # LLM 送信前の PII マスキングに Cloud DLP を使うか（issue 296、既定 false）。true のときのみ DLP API を呼ぶ。
    DLP_ENABLED = tostring(var.dlp_enabled)
  }

  # service mints GitHub App installation tokens (method B) in the analysis pipelines,
  # so it needs the App private key — not just the api.
  service_secret_env = {
    DATABASE_URL           = "database-url"
    GITHUB_APP_PRIVATE_KEY = "github-app-private-key"
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

  # Accept Cloud Tasks OIDC tokens minted with this stable audience (the api uses the same
  # value). Avoids the service needing to know its own run.app URL (Terraform self-cycle).
  custom_audiences = [local.service_oidc_audience]

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

# The external HTTPS LB forwards requests to the api's serverless NEG WITHOUT credentials,
# so the api service must allow unauthenticated invocation or every request gets a 403.
# Access is still gated by the app's own auth (cookies) and Cloud Armor at the edge.
resource "google_cloud_run_v2_service_iam_member" "api_public" {
  name     = google_cloud_run_v2_service.api.name
  location = google_cloud_run_v2_service.api.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# Only the Cloud Tasks invoker SA may call service (OIDC). Never allUsers — external reach
# is the LB-fronted api only.
resource "google_cloud_run_v2_service_iam_member" "service_tasks_invoker" {
  name     = google_cloud_run_v2_service.service.name
  location = google_cloud_run_v2_service.service.location
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.tasks_invoker.email}"
}
