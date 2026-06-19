variable "repo_owner" {
  description = "GitHub organization or user that owns the repo."
  type        = string
}

variable "repo_name" {
  description = "GitHub repository name."
  type        = string
}

variable "gcp_project_id" {
  description = "Google Cloud project ID."
  type        = string
}

variable "region" {
  description = "GCP region. Must match infra/gcp/var.region."
  type        = string
  default     = "asia-northeast1"
}

variable "project_name" {
  description = "Project name used for resource naming. Must match infra/gcp/var.project_name."
  type        = string
  default     = "fullstack-app"
}

variable "environments" {
  description = "GitHub environment names. One WIF binding is created per entry."
  type        = list(string)
  default     = ["staging", "production"]
}

variable "state_bucket" {
  description = "GCS bucket name for tfstate (shared by app + bootstrap under different prefixes)."
  type        = string
  default     = "fullstack-app-tfstate"
}
