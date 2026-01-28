provider "google" {
  project = var.project_id
  region  = var.region
}

module "github_runner" {
  source  = "philips-labs/github-runner/google"
  version = "~> 6.0"

  github_app = {
    id             = var.github_app_id
    key            = var.github_app_private_key
    webhook_secret = var.github_webhook_secret
  }

  gcp_project_id = var.project_id
  gcp_region     = var.region

  runner_config = {
    runner_labels = var.runner_labels
    runner_group  = "default"
  }
}

output "runner_webhook_endpoint" {
  value = module.github_runner.webhook_endpoint
}
