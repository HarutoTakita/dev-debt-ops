# GCS bucket for request payloads that exceed the Cloud Tasks body limit (the `$requestRef`
# spillover from issue-016 — gs:// is the GCP analog of app_ref's blob://). Results never spill
# (service writes them straight to Cloud SQL), so this bucket only holds inbound requests.
resource "google_storage_bucket" "job_payloads" {
  name     = "${var.project_name}-${var.environment}-job-payloads"
  location = var.region

  uniform_bucket_level_access = true
  force_destroy               = var.environment != "prod"

  # Spilled requests are short-lived — drop them after a few days.
  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      age = 7
    }
  }

  depends_on = [google_project_service.services]
}

# Both runtime SAs read/write spilled payloads, scoped to this bucket only.
resource "google_storage_bucket_iam_member" "payloads_object_admin" {
  for_each = local.runtime_sas
  bucket   = google_storage_bucket.job_payloads.name
  role     = "roles/storage.objectAdmin"
  member   = "serviceAccount:${each.value}"
}
