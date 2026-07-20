output "bucket_name" {
  description = "Name of the created bucket."
  value       = google_storage_bucket.this.name
}

output "bucket_url" {
  description = "gs:// URL of the bucket (use as MLflow --default-artifact-root)."
  value       = "gs://${google_storage_bucket.this.name}"
}
