output "artifact_registry_repo" {
  description = "Artifact Registry Docker repository (push api/service images here)."
  value       = google_artifact_registry_repository.main.name
}

output "api_url" {
  description = "Public api endpoint (domain HTTPS if set, otherwise the LB IP to point DNS at)."
  value       = var.domain != "" ? "https://${var.domain}" : google_compute_global_address.lb_ip.address
}

output "lb_ip" {
  description = "External LB IP — create a DNS A record for var.domain pointing at this."
  value       = google_compute_global_address.lb_ip.address
}

output "service_url" {
  description = "Internal service (worker) Cloud Run URL — Cloud Tasks HTTP target."
  value       = google_cloud_run_v2_service.service.uri
}

output "db_connection_name" {
  description = "Cloud SQL connection name (project:region:instance) for the Cloud SQL connector."
  value       = google_sql_database_instance.main.connection_name
  sensitive   = true
}

output "job_payloads_bucket" {
  description = "GCS bucket for spilled request payloads (= JOB_PAYLOAD_BUCKET env)."
  value       = google_storage_bucket.job_payloads.name
}

output "tasks_queue_names" {
  description = "Cloud Tasks request queue names."
  value       = [for q in google_cloud_tasks_queue.queues : q.name]
}

# No job_results_topic output — results are written to Cloud SQL, not Pub/Sub.
