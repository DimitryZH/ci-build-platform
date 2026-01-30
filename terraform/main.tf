module "gce_runners" {
  source = "./gce-runners"

  project_id  = var.project_id
  environment = var.environment
  zone        = var.zone

  service_account_email = var.runner_service_account_email

  github_token = var.github_token
  github_org   = var.github_org
  github_repo  = var.github_repo
}

module "cloud_run_controller" {
  source = "./cloud-run-controller"

  project_id  = var.project_id
  region      = var.region
  environment = var.environment

  controller_image      = var.controller_image
  service_account_email = var.controller_service_account_email

  github_org       = var.github_org
  github_repo      = var.github_repo
  controller_token = var.controller_token
}

module "monitoring" {
  source = "./monitoring"

  project_id            = var.project_id
  notification_channels = var.notification_channels
}

