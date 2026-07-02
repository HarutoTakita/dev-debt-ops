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

# service だけが LLM を呼ぶ（マスキングも service 内）。DLP_ENABLED=true 時に deidentifyContent を
# 呼ぶため service SA に roles/dlp.user を付与（issue 296）。無効時は未使用。
resource "google_project_iam_member" "service_dlp" {
  project = var.gcp_project_id
  role    = "roles/dlp.user"
  member  = "serviceAccount:${google_service_account.service.email}"
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

data "google_project" "current" {
  project_id = var.gcp_project_id
}

# api builds Cloud Tasks tasks carrying an OIDC token minted as tasks_invoker. Creating a task
# with another SA's token requires actAs on that SA — without this, create_task → PERMISSION_DENIED.
resource "google_service_account_iam_member" "api_actas_tasks_invoker" {
  service_account_id = google_service_account.tasks_invoker.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.api.email}"
}

# At dispatch the Cloud Tasks service agent mints the OIDC token AS tasks_invoker, which needs
# the Token Creator role on that SA — without this, delivery fails before reaching service.
resource "google_service_account_iam_member" "cloudtasks_mint_tasks_invoker" {
  service_account_id = google_service_account.tasks_invoker.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-cloudtasks.iam.gserviceaccount.com"
}
