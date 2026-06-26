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
    GITHUB_APP_ID         = var.github_app_id
    GITHUB_APP_SLUG       = var.github_app_slug
    GITHUB_CLIENT_ID      = var.github_client_id
    FRONTEND_ORIGIN       = var.domain != "" ? "https://${var.domain}" : "http://localhost:5173"
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
    # stg: the worker is already gated by Cloud Run IAM (internal-only ingress +
    # tasks_invoker-only run.invoker), so skip the redundant app-level OIDC check, whose
    # expected audience can't be wired without a self-referential service URL. prod keeps
    # fail-closed app-level OIDC (issue-038) and needs the audience wired before prod deploy.
    USE_MOCK_QUEUE = var.environment == "prod" ? "false" : "true"
    GITHUB_APP_ID  = var.github_app_id
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
