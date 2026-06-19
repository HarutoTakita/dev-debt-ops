# Enable the GCP APIs this stack needs. `disable_on_destroy = false` avoids tearing
# down shared-project APIs when this stack is destroyed.
#
# Intentionally NOT enabled: pubsub / cloudfunctions / cloudscheduler / eventarc.
# The online path has no Pub/Sub (service writes results straight to Cloud SQL), and
# scheduled-scan Functions/Scheduler are a future, dedicated issue.
resource "google_project_service" "services" {
  for_each = toset([
    "run.googleapis.com",
    "cloudtasks.googleapis.com",
    "sqladmin.googleapis.com",
    "secretmanager.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "compute.googleapis.com",
    "vpcaccess.googleapis.com",
    "servicenetworking.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "aiplatform.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "cloudtrace.googleapis.com",
  ])

  service            = each.value
  disable_on_destroy = false
}
