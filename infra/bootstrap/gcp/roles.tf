# Project-level roles for the deploy SA, grouped by concern (mirrors aws's scoped deploy
# policy). roles/iam.serviceAccountUser is required so the deploy SA can actAs the runtime SAs
# when assigning them to Cloud Run.
#
# Intentionally NOT granted: roles/pubsub.admin, roles/cloudfunctions.admin,
# roles/cloudscheduler.admin — this issue creates none of those resources. A future
# scheduled-scan issue adds them there.
locals {
  deploy_roles = toset([
    "roles/run.admin",                       # Cloud Run services
    "roles/cloudtasks.admin",                # Cloud Tasks queues
    "roles/cloudsql.admin",                  # Cloud SQL instance/db/user
    "roles/secretmanager.admin",             # Secret Manager secrets + IAM
    "roles/artifactregistry.admin",          # Docker repo
    "roles/iam.serviceAccountAdmin",         # create runtime SAs
    "roles/iam.serviceAccountUser",          # actAs runtime SAs → Cloud Run
    "roles/storage.admin",                   # tfstate + payload buckets
    "roles/compute.admin",                     # LB / Cloud Armor / VPC
    "roles/vpcaccess.admin",                   # Serverless VPC Access connector
    "roles/servicenetworking.networksAdmin",   # private services access peering (Cloud SQL)
    "roles/monitoring.editor",                 # alert policies + uptime checks (monitoring.tf)
    "roles/logging.configWriter",              # log-based metrics (monitoring.tf)
    "roles/serviceusage.serviceUsageAdmin",    # enable APIs
    "roles/iam.workloadIdentityPoolAdmin",     # manage WIF if needed
    "roles/resourcemanager.projectIamAdmin",   # bind runtime SA project roles (iam.tf in app stack)
  ])
}

resource "google_project_iam_member" "deploy" {
  for_each = local.deploy_roles
  project  = var.gcp_project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.github_deploy.email}"
}
