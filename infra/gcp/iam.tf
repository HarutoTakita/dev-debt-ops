# Runtime + dispatcher service accounts and their project-level role bindings.
# Secret- and bucket-scoped bindings live next to those resources (secrets.tf / storage.tf);
# this file is the single place to read the SA topology and project-wide grants.
#
# No Pub/Sub SA/roles and no functions SA: the online path has no Pub/Sub, and
# scheduled-scan Functions are out of scope.

# api runtime SA — external (LB-fronted) Cloud Run service.
resource "google_service_account" "api" {
  account_id   = "${var.project_name}-${var.environment}-api"
  display_name = "Rosetta api runtime (${var.environment})"
}

# service runtime SA — internal worker Cloud Run service.
resource "google_service_account" "service" {
  account_id   = "${var.project_name}-${var.environment}-svc"
  display_name = "Rosetta service runtime (${var.environment})"
}

# tasks_invoker SA — the identity Cloud Tasks mints OIDC tokens as to call service.
resource "google_service_account" "tasks_invoker" {
  account_id   = "${var.project_name}-${var.environment}-tasks"
  display_name = "Rosetta Cloud Tasks invoker (${var.environment})"
}

locals {
  # Both runtime SAs connect to Cloud SQL (api: migrations + queries; service: Job UPDATE)
  # and use Vertex AI (no API key — the google-api-key difference from azure/aws).
  runtime_sas = {
    api     = google_service_account.api.email
    service = google_service_account.service.email
  }
}

resource "google_project_iam_member" "runtime_cloudsql" {
  for_each = local.runtime_sas
  project  = var.gcp_project_id
  role     = "roles/cloudsql.client"
  member   = "serviceAccount:${each.value}"
}

resource "google_project_iam_member" "runtime_aiplatform" {
  for_each = local.runtime_sas
  project  = var.gcp_project_id
  role     = "roles/aiplatform.user"
  member   = "serviceAccount:${each.value}"
}

# api enqueues Cloud Tasks; service does not.
resource "google_project_iam_member" "api_tasks_enqueuer" {
  project = var.gcp_project_id
  role    = "roles/cloudtasks.enqueuer"
  member  = "serviceAccount:${google_service_account.api.email}"
}

# Let both runtime SAs write logs / metrics / traces explicitly (Cloud Run usually
# grants this, but pinning it keeps the topology self-documenting).
resource "google_project_iam_member" "runtime_logging" {
  for_each = local.runtime_sas
  project  = var.gcp_project_id
  role     = "roles/logging.logWriter"
  member   = "serviceAccount:${each.value}"
}
