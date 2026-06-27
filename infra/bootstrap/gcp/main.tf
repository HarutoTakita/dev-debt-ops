terraform {
  required_version = ">= 1.11.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 7.38"
    }
  }

  # Bootstrap state lives in the same tfstate bucket as the app stack but under a separate
  # prefix so the two never lock each other (mirrors azure's separate key / aws's separate path).
  #
  # Chicken-and-egg: this stack CREATES the bucket it stores state in. First run uses the local
  # backend, then migrate:
  #   1. comment out this `backend "gcs"` block
  #   2. terraform init && terraform apply   (creates the bucket via state.tf)
  #   3. uncomment the block, then: terraform init -migrate-state
  backend "gcs" {
    bucket = "dev-debt-ops"
    prefix = "gcp/bootstrap/"
  }
}

provider "google" {
  project = var.gcp_project_id
  region  = var.region
}

data "google_project" "current" {}
