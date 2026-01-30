# Monitoring
# -------------------------------
# Log-based metric: CI Runner Errors
# -------------------------------
resource "google_logging_metric" "ci_runner_errors" {
  name        = "ci_runner_errors"
  description = "Count of error logs from CI runners"

  filter = <<EOT
resource.type="gce_instance"
labels."compute.googleapis.com/resource_name" =~ "ci-runner"
severity>=ERROR
EOT

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"
  }
}

# -------------------------------
# Log-based metric: Cloud Run Controller Errors
# -------------------------------
resource "google_logging_metric" "controller_errors" {
  name        = "ci_controller_errors"
  description = "Errors from Cloud Run CI controller"

  filter = <<EOT
resource.type="cloud_run_revision"
resource.labels.service_name="ci-runner-controller"
severity>=ERROR
EOT

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"
  }
}

# -------------------------------
# Alert Policy: CI Infrastructure Errors
# -------------------------------
resource "google_monitoring_alert_policy" "ci_errors_alert" {
  display_name = "CI Platform Errors"
  combiner     = "OR"

  conditions {
    display_name = "CI Runner Errors"

    condition_threshold {
      filter          = "metric.type=\"logging.googleapis.com/user/ci_runner_errors\""
      duration        = "60s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_DELTA"
      }
    }
  }

  conditions {
    display_name = "Cloud Run Controller Errors"

    condition_threshold {
      filter          = "metric.type=\"logging.googleapis.com/user/ci_controller_errors\""
      duration        = "60s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_DELTA"
      }
    }
  }

  notification_channels = var.notification_channels
}
