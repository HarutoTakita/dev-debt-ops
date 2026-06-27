# Static landing page (LP) hosting — Option A: a GCS bucket served as a backend bucket on the
# SAME external HTTPS LB as the app, host-routed by var.lp_domain. The LP deploys independently
# of the app (CI just uploads the static files to this bucket; no Cloud Run rebuild).
# All LP resources are gated on var.lp_domain so `terraform plan` still passes when it is unset.
locals {
  lp_enabled = var.lp_domain != ""
}

resource "google_storage_bucket" "landing" {
  count    = local.lp_enabled ? 1 : 0
  name     = "${var.project_name}-${var.environment}-landing"
  location = var.region

  uniform_bucket_level_access = true
  force_destroy               = var.environment != "prod"

  website {
    main_page_suffix = "index.html"
    not_found_page   = "index.html"
  }

  depends_on = [google_project_service.services]
}

# Public read so the LB backend bucket can serve the static LP to anonymous visitors.
# (Requires the bucket to allow public access — disable "public access prevention" at the
# org/project level if enforced.)
resource "google_storage_bucket_iam_member" "landing_public" {
  count  = local.lp_enabled ? 1 : 0
  bucket = google_storage_bucket.landing[0].name
  role   = "roles/storage.objectViewer"
  member = "allUsers"
}

resource "google_compute_backend_bucket" "landing" {
  count       = local.lp_enabled ? 1 : 0
  name        = "${local.name_prefix}-landing-be"
  bucket_name = google_storage_bucket.landing[0].name
  enable_cdn  = true
}
