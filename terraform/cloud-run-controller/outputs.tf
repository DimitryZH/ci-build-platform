output "controller_url" {
  description = "Cloud Run controller URL"
  value       = google_cloud_run_service.runner_controller.status[0].url
}
