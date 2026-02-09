variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "region" {
  description = "Cloud Run region"
  type        = string
  default     = "us-central1"
}

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "runner_service_account_email" {
  description = "Service account email used by GCE runners (passed through to TF in controller container)"
  type        = string
}

variable "controller_token" {
  description = "Shared secret token used by GitHub to call the Cloud Run controller"
  type        = string
  sensitive   = true
}

variable "controller_image" {
  description = "Docker image for Cloud Run controller"
  type        = string
}

variable "service_account_email" {
  description = "Service account used by Cloud Run"
  type        = string
}

variable "github_token" {
  description = "GitHub token used by runners to register with GitHub Actions (passed through to TF in controller container)"
  type        = string
  sensitive   = true
}

variable "github_org" {
  description = "GitHub organization or user"
  type        = string
}

variable "github_repo" {
  description = "GitHub repository name"
  type        = string
}
