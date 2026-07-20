locals {
  common_labels = merge(var.labels, {
    environment = var.environment
  })
}

# -----------------------------------------------------------------------------
# Container image registry (Artifact Registry).
# -----------------------------------------------------------------------------
module "artifact_registry" {
  source        = "./modules/artifact-registry"
  project_id    = var.project_id
  region        = var.region
  repository_id = var.artifact_registry_repo
  description   = "Container images for the kubernetes-mlops-platform"
  labels        = local.common_labels
}

# -----------------------------------------------------------------------------
# MLflow artifact store (GCS bucket). Postgres holds MLflow *metadata*; large
# artifacts (models, plots) live here.
# -----------------------------------------------------------------------------
module "mlflow_artifacts" {
  source        = "./modules/gcs-bucket"
  project_id    = var.project_id
  location      = var.region
  name          = "${var.project_id}-${var.mlflow_artifacts_bucket}"
  force_destroy = var.environment != "prod"
  # Keep old model artifacts for 180 days, then delete to control cost.
  lifecycle_age_days = 180
  labels             = local.common_labels
}

# -----------------------------------------------------------------------------
# Autoscaled training node pool on an EXISTING GKE cluster. Spot VMs by default
# to keep batch training cheap; tainted so only training jobs schedule here.
# -----------------------------------------------------------------------------
resource "google_container_node_pool" "training" {
  name           = "training-pool"
  project        = var.project_id
  location       = var.region
  cluster        = var.cluster_name
  node_locations = var.gke_node_locations

  autoscaling {
    min_node_count = var.training_min_nodes
    max_node_count = var.training_max_nodes
  }

  management {
    auto_repair  = true
    auto_upgrade = true
  }

  node_config {
    machine_type = var.training_machine_type
    spot         = var.use_spot_nodes
    disk_size_gb = 100
    disk_type    = "pd-balanced"

    # Least-privilege node identity; app-level access uses Workload Identity.
    service_account = google_service_account.gke_nodes.email
    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform",
    ]

    # Required for Workload Identity to function on the node.
    workload_metadata_config {
      mode = "GKE_METADATA"
    }

    shielded_instance_config {
      enable_secure_boot          = true
      enable_integrity_monitoring = true
    }

    labels = local.common_labels

    # Dedicate this pool to training jobs.
    taint {
      key    = "workload"
      value  = "training"
      effect = "NO_SCHEDULE"
    }
  }

  lifecycle {
    ignore_changes = [node_config[0].labels]
  }
}

# -----------------------------------------------------------------------------
# GKE node service account (least privilege).
# -----------------------------------------------------------------------------
resource "google_service_account" "gke_nodes" {
  project      = var.project_id
  account_id   = "gke-nodes-${var.environment}"
  display_name = "GKE node identity (${var.environment})"
}

# Minimal roles for nodes: logging, monitoring, and pulling images.
resource "google_project_iam_member" "gke_nodes_roles" {
  for_each = toset([
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
    "roles/monitoring.viewer",
    "roles/artifactregistry.reader",
  ])
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.gke_nodes.email}"
}

# -----------------------------------------------------------------------------
# Workload Identity: a Google SA the ml-api pods impersonate to reach GCS
# (artifact store) without static keys.
# -----------------------------------------------------------------------------
resource "google_service_account" "ml_api" {
  project      = var.project_id
  account_id   = "ml-api-${var.environment}"
  display_name = "ml-api workload identity (${var.environment})"
}

# Let the app read/write MLflow artifacts in the bucket.
resource "google_storage_bucket_iam_member" "ml_api_artifacts" {
  bucket = module.mlflow_artifacts.bucket_name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.ml_api.email}"
}

# Bind the Kubernetes SA (namespace/name) to the Google SA via Workload Identity.
resource "google_service_account_iam_member" "ml_api_workload_identity" {
  service_account_id = google_service_account.ml_api.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[${var.k8s_namespace}/${var.k8s_service_account}]"
}

# -----------------------------------------------------------------------------
# MLflow metadata backend.
# For a managed option use Cloud SQL for PostgreSQL (google_sql_database_instance).
# It is intentionally NOT provisioned here to avoid a standing cost in a demo /
# portfolio project; docker-compose runs a self-hosted Postgres for local dev,
# and README documents the Cloud SQL path. See terraform/README.md.
# -----------------------------------------------------------------------------
