variable "project_id" {
  description = "GCP project ID."
  type        = string
}

variable "name" {
  description = "Globally-unique bucket name."
  type        = string
}

variable "location" {
  description = "Bucket location (region or multi-region)."
  type        = string
}

variable "storage_class" {
  description = "Default storage class."
  type        = string
  default     = "STANDARD"
}

variable "force_destroy" {
  description = "Allow Terraform to delete a non-empty bucket (dev only)."
  type        = bool
  default     = false
}

variable "versioning" {
  description = "Enable object versioning (recommended for model artifacts)."
  type        = bool
  default     = true
}

variable "lifecycle_age_days" {
  description = "Delete objects older than N days (0 disables the rule)."
  type        = number
  default     = 0
}

variable "labels" {
  description = "Labels to apply to the bucket."
  type        = map(string)
  default     = {}
}
