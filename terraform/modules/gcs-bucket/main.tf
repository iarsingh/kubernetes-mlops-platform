resource "google_storage_bucket" "this" {
  project                     = var.project_id
  name                        = var.name
  location                    = var.location
  force_destroy               = var.force_destroy
  storage_class               = var.storage_class
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  labels                      = var.labels

  versioning {
    enabled = var.versioning
  }

  dynamic "lifecycle_rule" {
    for_each = var.lifecycle_age_days > 0 ? [1] : []
    content {
      condition {
        age = var.lifecycle_age_days
      }
      action {
        type = "Delete"
      }
    }
  }
}
