terraform {
  required_version = ">= 1.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }

  # ---------------------------------------------------------------------------
  # Remote state backend.
  # Commented out because no real GCS state bucket exists yet. To enable:
  #   1. Create the bucket:  gcloud storage buckets create gs://<PROJECT>-tfstate
  #   2. Uncomment and run:  terraform init -migrate-state
  # State locking on GCS is automatic (uses object generation preconditions).
  # ---------------------------------------------------------------------------
  # backend "gcs" {
  #   bucket = "REPLACE_ME-tfstate"
  #   prefix = "kubernetes-mlops-platform"
  # }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
