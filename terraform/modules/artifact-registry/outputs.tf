output "repository_id" {
  description = "Artifact Registry repository ID."
  value       = google_artifact_registry_repository.this.repository_id
}

output "repository_url" {
  description = "Docker repository URL for push/pull (LOCATION-docker.pkg.dev/PROJECT/REPO)."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.this.repository_id}"
}
