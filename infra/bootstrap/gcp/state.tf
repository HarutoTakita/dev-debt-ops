# GCS bucket holding tfstate for BOTH stacks (app under prefix gcp/, bootstrap under
# gcp/bootstrap/). See the chicken-and-egg note in main.tf: this bucket is created here but
# also backs this stack's own state, so the first apply runs against the local backend and is
# then migrated with `terraform init -migrate-state` (analogous to aws's shared-bucket and
# azure's same-container/different-key bootstrapping).
resource "google_storage_bucket" "tfstate" {
  name     = var.state_bucket
  location = var.region

  uniform_bucket_level_access = true
  force_destroy               = false

  versioning {
    enabled = true
  }

  depends_on = [google_project_service.bootstrap]
}
