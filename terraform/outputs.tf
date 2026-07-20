output "artifact_registry_repository" {
  description = "Full Artifact Registry repository path for docker push/pull."
  value       = module.artifact_registry.repository_url
}

output "mlflow_artifacts_bucket" {
  description = "GCS bucket used as the MLflow artifact store."
  value       = module.mlflow_artifacts.bucket_name
}

output "ml_api_gcp_service_account" {
  description = "Google SA email the ml-api pods impersonate (annotate the KSA with this)."
  value       = google_service_account.ml_api.email
}

output "gke_nodes_service_account" {
  description = "Least-privilege service account used by GKE nodes."
  value       = google_service_account.gke_nodes.email
}

output "training_node_pool" {
  description = "Name of the autoscaled (spot) training node pool."
  value       = google_container_node_pool.training.name
}

output "workload_identity_annotation" {
  description = "Value to set on the KSA annotation iam.gke.io/gcp-service-account."
  value       = google_service_account.ml_api.email
}
