# Cloud Run controller service
resource "google_cloud_run_service" "runner_controller" {
  name     = "ci-runner-controller"
  location = var.region

  template {
    spec {
      containers {
        image = var.controller_image

        ports {
          container_port = 8080
        }

        # General context
        env {
          name  = "PROJECT_ID"
          value = var.project_id
        }

        # Root Terraform variables (used by controller when running terraform)
        env {
          name  = "TF_VAR_project_id"
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

        env {
          name  = "TF_VAR_runner_service_account_email"
          value = var.runner_service_account_email
        }

        env {
          name  = "TF_VAR_controller_service_account_email"
          value = var.service_account_email
        }

        env {
          name  = "TF_VAR_github_token"
          value = var.github_token
        }

        env {
          name  = "TF_VAR_controller_image"
          value = var.controller_image
        }

        env {
          name  = "TF_VAR_controller_token"
          value = var.controller_token
        }

        # Controller auth token (checked by Flask app)
        env {
          name  = "GITHUB_CONTROLLER_TOKEN"
          value = var.controller_token
        }
      }

      # Service account that runs the Cloud Run revision
      service_account_name = var.service_account_email
    }
  }

  traffic {
    percent         = 100
    latest_revision = true
  }
}

# Allow unauthenticated HTTP access (auth is handled by X-Controller-Token)
resource "google_cloud_run_service_iam_member" "public_invoker" {
  service  = google_cloud_run_service.runner_controller.name
  location = google_cloud_run_service.runner_controller.location

  role   = "roles/run.invoker"
  member = "allUsers"
}
