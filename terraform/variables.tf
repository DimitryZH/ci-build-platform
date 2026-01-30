variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "region" {
  description = "Default GCP region"
  type        = string
  default     = "us-central1"
}

variable "environment" {
  description = "Environment name (dev, stage, prod)"
  type        = string
  default     = "dev"
}

variable "github_org" {
  description = "GitHub organization or user"
  type        = string
}

variable "github_repo" {
  description = "GitHub repository name"
  type        = string
}

variable "zone" {
  description = "Default GCE zone for runners"
  type        = string
  default     = "us-central1-a"
}

variable "runner_service_account_email" {
  description = "Service account email used by GCE runners"
  type        = string
}

variable "controller_service_account_email" {
  description = "Service account email used by the Cloud Run controller"
  type        = string
}

variable "github_token" {
  description = "GitHub token used by runners to register with GitHub Actions"
  type        = string
  sensitive   = true
}

variable "controller_image" {
  description = "Container image for the Cloud Run controller"
  type        = string
}

variable "controller_token" {
  description = "Shared secret token used by GitHub to authenticate to the Cloud Run controller"
  type        = string
  sensitive   = true
}

variable "notification_channels" {
  description = "List of Monitoring notification channel IDs"
  type        = list(string)
  default     = []
}

