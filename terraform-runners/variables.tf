variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "us-central1"
}

variable "github_app_id" {
  description = "GitHub App ID for runner authentication"
  type        = string
}

variable "github_app_private_key" {
  description = "GitHub App private key"
  type        = string
  sensitive   = true
}

variable "github_webhook_secret" {
  description = "GitHub webhook secret"
  type        = string
  sensitive   = true
}

variable "runner_labels" {
  description = "Labels assigned to GitHub runners"
  type        = list(string)
  default     = ["self-hosted", "ephemeral", "gce"]
}
