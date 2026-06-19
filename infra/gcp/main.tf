terraform {
  required_version = ">= 1.11.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 6.0"
    }
  }

  # App-stack state lives in the shared tfstate bucket under the `gcp/` prefix.
  # The bootstrap stack uses `gcp/bootstrap/` so the two never lock each other
  # (mirrors azure's separate `key` and aws's separate state path).
  backend "gcs" {
    bucket = "fullstack-app-tfstate"
    prefix = "gcp/"
  }
}

locals {
  # Postgres DB names cannot contain hyphens.
  db_name = replace(var.project_name, "-", "_")

  region_short = lookup({
    "asia-northeast1" = "an1"
    "asia-northeast2" = "an2"
    "us-central1"     = "uc1"
  }, var.region, replace(var.region, "-", ""))

  name_prefix = "${var.project_name}-${local.region_short}-${var.environment}"
}

provider "google" {
  project = var.gcp_project_id
  region  = var.region

  default_labels = {
    project     = var.project_name
    environment = var.environment
    managed-by  = "terraform"
  }
}

provider "google-beta" {
  project = var.gcp_project_id
  region  = var.region

  default_labels = {
    project     = var.project_name
    environment = var.environment
    managed-by  = "terraform"
  }
}
