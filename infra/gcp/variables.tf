variable "project_name" {
  description = "Project name used for resource naming. Must match infra/bootstrap/gcp."
  type        = string
  default     = "fullstack-app"
}

variable "environment" {
  description = "Environment (stg or prod)."
  type        = string
}

variable "gcp_project_id" {
  description = "Google Cloud project ID to deploy into."
  type        = string
}

variable "region" {
  description = "GCP region for Cloud Run / Cloud SQL / Cloud Tasks / Vertex AI (single region)."
  type        = string
  default     = "asia-northeast1"
}

# --- Database ---

variable "db_username" {
  description = "Cloud SQL database user."
  type        = string
  default     = "postgres"
  sensitive   = true
}

variable "db_password" {
  description = "Cloud SQL database user password."
  type        = string
  sensitive   = true
}

variable "db_tier" {
  description = "Cloud SQL machine tier (e.g. db-f1-micro, db-custom-2-7680)."
  type        = string
  default     = "db-f1-micro"
}

variable "db_disk_size" {
  description = "Cloud SQL data disk size in GB."
  type        = number
  default     = 10
}

variable "db_backup_enabled" {
  description = "Enable Cloud SQL automated backups (recommended for prod)."
  type        = bool
  default     = false
}

# --- Secrets (never written to tfvars; injected via TF_VAR_* from CI) ---

variable "secret_key" {
  description = "Application secret key for JWT signing."
  type        = string
  sensitive   = true
}

variable "github_app_private_key" {
  description = "GitHub App RSA private key (PEM)."
  type        = string
  sensitive   = true
}

variable "github_client_secret" {
  description = "GitHub OAuth App client secret."
  type        = string
  sensitive   = true
}

variable "github_webhook_secret" {
  description = "GitHub webhook signing secret."
  type        = string
  sensitive   = true
  default     = ""
}

# Non-secret GitHub identifiers (safe to keep in tfvars). Required for the deployed app to
# mint installation tokens (App ID, service-side) and run OAuth login (Client ID / slug, api-side).
variable "github_app_id" {
  description = "GitHub App numeric ID."
  type        = string
  default     = ""
}

variable "github_app_slug" {
  description = "GitHub App slug (URL name)."
  type        = string
  default     = ""
}

variable "github_client_id" {
  description = "GitHub OAuth client ID."
  type        = string
  default     = ""
}

# NOTE: there is intentionally NO `google_api_key` variable. AI uses Vertex AI via ADC
# (the runtime SAs get roles/aiplatform.user), so no API key Secret is needed — the key
# difference from infra/azure and infra/aws, which do create a google-api-key secret.

# --- Container images (injected by the deploy workflow; stub default for plan/validate) ---

variable "container_image_api" {
  description = "Container image URI for the api Cloud Run service."
  type        = string
  default     = "gcr.io/cloudrun/hello"
}

variable "container_image_service" {
  description = "Container image URI for the service (worker) Cloud Run service."
  type        = string
  default     = "gcr.io/cloudrun/hello"
}

# --- Cloud Run sizing (per service) ---

variable "api_cpu" {
  description = "CPU for the api service (e.g. \"1\", \"2\")."
  type        = string
  default     = "1"
}

variable "api_memory" {
  description = "Memory for the api service (e.g. \"512Mi\", \"1Gi\")."
  type        = string
  default     = "512Mi"
}

variable "api_min_instances" {
  description = "Minimum instances for the api service."
  type        = number
  default     = 0
}

variable "api_max_instances" {
  description = "Maximum instances for the api service."
  type        = number
  default     = 5
}

variable "api_timeout" {
  description = "Request timeout for the api service (e.g. \"300s\")."
  type        = string
  default     = "300s"
}

variable "service_cpu" {
  description = "CPU for the worker service (heavy processing)."
  type        = string
  default     = "2"
}

variable "service_memory" {
  description = "Memory for the worker service."
  type        = string
  default     = "2Gi"
}

variable "service_min_instances" {
  description = "Minimum instances for the worker service."
  type        = number
  default     = 0
}

variable "service_max_instances" {
  description = "Maximum instances for the worker service."
  type        = number
  default     = 10
}

variable "service_timeout" {
  description = "Request (task) timeout for the worker service — long for heavy jobs."
  type        = string
  default     = "1800s"
}

# --- Cloud Tasks ---

variable "task_pipelines" {
  description = "Cloud Tasks request queue names to create (one per logical pipeline grouping). issue-016's dispatcher uses a single queue by default."
  type        = list(string)
  default     = ["job-requests"]
}

variable "tasks_queue" {
  description = "Queue name injected as TASKS_QUEUE (016 Settings name). Must be in task_pipelines."
  type        = string
  default     = "job-requests"
}

variable "tasks_max_dispatches_per_second" {
  description = "Cloud Tasks queue max dispatch rate."
  type        = number
  default     = 10
}

variable "tasks_max_concurrent_dispatches" {
  description = "Cloud Tasks queue max concurrent dispatches."
  type        = number
  default     = 20
}

variable "tasks_max_attempts" {
  description = "Cloud Tasks retry max attempts (at-least-once; app is idempotent)."
  type        = number
  default     = 5
}

variable "tasks_min_backoff" {
  description = "Cloud Tasks retry minimum backoff."
  type        = string
  default     = "5s"
}

variable "tasks_max_backoff" {
  description = "Cloud Tasks retry maximum backoff."
  type        = string
  default     = "300s"
}

# --- Networking / edge ---

variable "domain" {
  description = "Domain for the external HTTPS load balancer + managed cert. Empty = LB frontend (cert/proxy/forwarding-rule) is skipped so plan still passes."
  type        = string
  default     = ""
}

# NOTE: there is intentionally NO `pubsub_push_source_ranges` and NO `container_image_functions`
# variable — the online path has no Pub/Sub push receiver (service writes results straight to
# Cloud SQL) and scheduled-scan Cloud Functions are out of scope for this issue.
