# Runtime secrets in Secret Manager, referenced by Cloud Run (env value_source) rather than
# passed as plaintext. Cleartext only lives in the Secret Manager data plane.
#
# NO `google-api-key` secret: AI uses Vertex AI via ADC (runtime SAs get roles/aiplatform.user
# in iam.tf), so there is no API key to store — the deliberate difference from infra/azure and
# infra/aws, which both create a google-api-key secret.
locals {
  # DATABASE_URL for Cloud Run → Cloud SQL over the unix socket mounted at /cloudsql/<conn>.
  database_url = "postgresql+asyncpg://${var.db_username}:${var.db_password}@/${local.db_name}?host=/cloudsql/${google_sql_database_instance.main.connection_name}"

  secrets = {
    "secret-key"             = var.secret_key
    "github-app-private-key" = var.github_app_private_key
    "github-client-secret"   = var.github_client_secret
    "github-webhook-secret"  = var.github_webhook_secret
    "database-url"           = local.database_url
  }
}

resource "google_secret_manager_secret" "secrets" {
  for_each  = local.secrets
  secret_id = "${var.project_name}-${var.environment}-${each.key}"

  replication {
    auto {}
  }

  depends_on = [google_project_service.services]
}

resource "google_secret_manager_secret_version" "secrets" {
  for_each    = local.secrets
  secret      = google_secret_manager_secret.secrets[each.key].id
  secret_data = each.value
}

# Grant each runtime SA accessor on exactly the secrets it needs.
locals {
  api_secret_keys     = ["secret-key", "github-app-private-key", "github-client-secret", "github-webhook-secret", "database-url"]
  service_secret_keys = ["database-url", "github-app-private-key"]

  secret_accessors = merge(
    { for k in local.api_secret_keys : "api-${k}" => { key = k, sa = google_service_account.api.email } },
    { for k in local.service_secret_keys : "service-${k}" => { key = k, sa = google_service_account.service.email } },
  )
}

resource "google_secret_manager_secret_iam_member" "accessors" {
  for_each  = local.secret_accessors
  secret_id = google_secret_manager_secret.secrets[each.value.key].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${each.value.sa}"
}
