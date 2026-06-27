output "workload_identity_provider" {
  description = "Full WIF provider resource name. Paste into the GitHub variable GCP_WIF_PROVIDER."
  value       = google_iam_workload_identity_pool_provider.github.name
}

output "deploy_service_account_email" {
  description = "Deploy SA email. Paste into the GitHub variable GCP_DEPLOY_SA."
  value       = google_service_account.github_deploy.email
}

output "gemini_service_account_email" {
  description = "Gemini PR review SA email. Paste into the GitHub variable GCP_GEMINI_SA."
  value       = google_service_account.github_gemini.email
}

output "state_bucket" {
  description = "tfstate bucket name (app stack uses prefix gcp/, bootstrap uses gcp/bootstrap/)."
  value       = google_storage_bucket.tfstate.name
}
