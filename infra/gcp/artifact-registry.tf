# Single Docker repository for both api and service images (differentiated by image name/tag).
# No functions image is built in this issue.
resource "google_artifact_registry_repository" "main" {
  repository_id = "${var.project_name}-${var.environment}"
  location      = var.region
  format        = "DOCKER"
  description   = "Rosetta container images (api / service) for ${var.environment}"

  depends_on = [google_project_service.services]
}
