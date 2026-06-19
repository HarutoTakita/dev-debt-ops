# Cloud Tasks request queue(s). api enqueues HTTP tasks targeting service's
# /tasks/{pipeline} with an OIDC token (the dispatch URL + OIDC are set by the app at
# enqueue time — issue-016 — so only the queue body lives here). Retry/backoff/rate limits
# are the Cloud Tasks-native substitute for a DLQ; permanent failures land as Job(FAILED).
#
# issue-016's dispatcher uses a single queue (default "job-requests"); `for_each` allows
# splitting per pipeline later without reshaping this file.
resource "google_cloud_tasks_queue" "queues" {
  for_each = toset(var.task_pipelines)

  name     = each.value
  location = var.region

  rate_limits {
    max_dispatches_per_second = var.tasks_max_dispatches_per_second
    max_concurrent_dispatches = var.tasks_max_concurrent_dispatches
  }

  retry_config {
    max_attempts  = var.tasks_max_attempts
    min_backoff   = var.tasks_min_backoff
    max_backoff   = var.tasks_max_backoff
    max_doublings = 4
  }

  depends_on = [google_project_service.services]
}
