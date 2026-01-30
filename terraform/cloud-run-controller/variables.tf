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

variable "controller_image" {
  description = "Docker image for Cloud Run controller"
  type        = string
}

variable "service_account_email" {
  description = "Service account used by Cloud Run"
  type        = string
}

variable "github_org" {
  description = "GitHub organization or user"
  type        = string
}

variable "github_repo" {
  description = "GitHub repository name"
  type        = string
}
