resource "google_artifact_registry_repository" "this" {
  project       = var.project_id
  location      = var.region
  repository_id = var.repository_id
  description   = var.description
  format        = "DOCKER"
  labels        = var.labels

  docker_config {
    immutable_tags = var.immutable_tags
  }

  # Auto-clean untagged images older than 30 days to control storage cost.
  cleanup_policies {
    id     = "delete-untagged"
    action = "DELETE"
    condition {
      tag_state  = "UNTAGGED"
      older_than = "2592000s" # 30 days
    }
  }

  # Always keep the most recent tagged releases.
  cleanup_policies {
    id     = "keep-recent-tagged"
    action = "KEEP"
    most_recent_versions {
      keep_count = 10
    }
  }
}
