# Minimal APIs the bootstrap stack itself needs (WIF + tfstate bucket + project IAM),
# plus Vertex AI which the deploy SA uses from the Gemini PR review CI
# (.github/workflows/pr-review.yml).
resource "google_project_service" "bootstrap" {
  for_each = toset([
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "sts.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "storage.googleapis.com",
    "serviceusage.googleapis.com",
    "aiplatform.googleapis.com",
  ])

  service            = each.value
  disable_on_destroy = false
}
