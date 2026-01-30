# Cloud Run controller
resource "google_cloud_run_service" "runner_controller" {
  name     = "ci-runner-controller"
  location = var.region

  template {
    spec {
      containers {
        image = var.controller_image

        env {
          name  = "PROJECT_ID"
          value = var.project_id
        }

        env {
          name  = "TF_VAR_environment"
          value = var.environment
        }

        env {
          name  = "TF_VAR_github_org"
          value = var.github_org
        }

        env {
          name  = "TF_VAR_github_repo"
          value = var.github_repo
        }
      }

      service_account_name = var.service_account_email
    }
  }

  traffic {
    percent         = 100
    latest_revision = true
  }
}
