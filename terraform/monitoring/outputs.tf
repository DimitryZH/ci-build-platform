output "ci_runner_error_metric" {
  description = "Log-based metric for CI runner errors"
  value       = google_logging_metric.ci_runner_errors.name
}

output "controller_error_metric" {
  description = "Log-based metric for Cloud Run controller errors"
  value       = google_logging_metric.controller_errors.name
}
