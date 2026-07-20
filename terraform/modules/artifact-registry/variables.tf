variable "project_id" {
  description = "GCP project ID."
  type        = string
}

variable "region" {
  description = "Region for the Artifact Registry repository."
  type        = string
}

variable "repository_id" {
  description = "Repository name (e.g. mlops)."
  type        = string
}

variable "description" {
  description = "Human-readable repository description."
  type        = string
  default     = "Container images"
}

variable "immutable_tags" {
  description = "Reject re-pushing an existing tag (enforces immutable releases)."
  type        = bool
  default     = true
}

variable "labels" {
  description = "Labels to apply to the repository."
  type        = map(string)
  default     = {}
}
