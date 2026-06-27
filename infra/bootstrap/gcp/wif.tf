# Workload Identity Federation for GitHub Actions — no long-lived keys. The deploy SA is
# usable only from this repo's workflows, pinned per GitHub environment (so production's
# required-reviewers gate also gates GCP deploys). Equivalent to azure's federated credential
# (subject = repo:.../:environment:<env>) and aws's OIDC trust sub condition.
resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "${var.project_name}-gh-pool"
  display_name              = "GitHub Actions"
  description               = "WIF pool for ${var.repo_owner}/${var.repo_name} GitHub Actions"

  depends_on = [google_project_service.bootstrap]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-oidc"
  display_name                       = "GitHub OIDC"

  attribute_mapping = {
    "google.subject"        = "assertion.sub"
    "attribute.repository"  = "assertion.repository"
    "attribute.environment" = "assertion.environment"
  }

  # Restrict the provider to this repository (the per-environment binding below narrows further).
  attribute_condition = "assertion.repository == \"${var.repo_owner}/${var.repo_name}\""

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account" "github_deploy" {
  account_id   = "${var.project_name}-gh-deploy"
  display_name = "GitHub Actions deploy (Terraform)"
}

# Allow each GitHub environment to impersonate the deploy SA. Combined with the provider's
# repository attribute_condition, this pins auth to repo + environment.
resource "google_service_account_iam_member" "wif_env" {
  for_each = toset(var.environments)

  service_account_id = google_service_account.github_deploy.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.environment/${each.value}"
}

# Least-privilege SA for the Gemini PR review CI (.github/workflows/pr-review.yml). Reuses the
# same pool/provider and per-environment impersonation as the deploy SA, but carries only
# roles/aiplatform.user (roles.tf) so the review agent can reach Vertex AI and nothing else.
resource "google_service_account" "github_gemini" {
  account_id   = "${var.project_name}-gh-gemini"
  display_name = "GitHub Actions Gemini PR review"
}

resource "google_service_account_iam_member" "wif_gemini_env" {
  for_each = toset(var.environments)

  service_account_id = google_service_account.github_gemini.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.environment/${each.value}"
}
