variable "project_id" {
  description = "GCP project ID that owns all resources."
  type        = string
}

variable "region" {
  description = "Primary GCP region (e.g. europe-west1)."
  type        = string
  default     = "europe-west1"
}

variable "environment" {
  description = "Environment name used for labels and resource naming."
  type        = string
  default     = "prod"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be one of: dev, staging, prod."
  }
}

variable "cluster_name" {
  description = "Name of the (existing) GKE cluster to attach the node pool to."
  type        = string
  default     = "mlops-gke"
}

variable "gke_node_locations" {
  description = "Zones the node pool spans (multi-zone for resilience)."
  type        = list(string)
  default     = ["europe-west1-b", "europe-west1-c"]
}

variable "training_machine_type" {
  description = "Machine type for the training node pool."
  type        = string
  default     = "e2-standard-4"
}

variable "training_min_nodes" {
  description = "Minimum nodes in the autoscaled training pool."
  type        = number
  default     = 0
}

variable "training_max_nodes" {
  description = "Maximum nodes in the autoscaled training pool."
  type        = number
  default     = 4
}

variable "use_spot_nodes" {
  description = "Use Spot VMs for the training pool (cheap, preemptible)."
  type        = bool
  default     = true
}

variable "artifact_registry_repo" {
  description = "Artifact Registry repository name for container images."
  type        = string
  default     = "mlops"
}

variable "mlflow_artifacts_bucket" {
  description = "Base name for the GCS bucket used as the MLflow artifact store. The project id is appended for global uniqueness."
  type        = string
  default     = "mlflow-artifacts"
}

variable "k8s_namespace" {
  description = "Kubernetes namespace the workloads run in (for Workload Identity binding)."
  type        = string
  default     = "mlops"
}

variable "k8s_service_account" {
  description = "Kubernetes ServiceAccount name bound via Workload Identity."
  type        = string
  default     = "ml-api"
}

variable "labels" {
  description = "Common labels applied to all resources."
  type        = map(string)
  default = {
    managed-by = "terraform"
    part-of    = "kubernetes-mlops-platform"
  }
}
