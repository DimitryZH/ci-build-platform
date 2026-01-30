variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "notification_channels" {
  description = "List of Monitoring notification channel IDs"
  type        = list(string)
  default     = []
}
