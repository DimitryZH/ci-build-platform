# GCE runners
resource "google_compute_instance" "runner" {
  name         = "ci-runner-${var.environment}"
  machine_type = var.machine_type
  zone         = var.zone

  tags = ["ci-runner"]

  boot_disk {
    initialize_params {
      image = var.boot_image
      size  = var.disk_size_gb
    }
  }

  network_interface {
    network = "default"
    access_config {}
  }

  metadata = {
    startup-script = templatefile("${path.module}/startup-script.sh", {
      github_token = var.github_token
      github_org   = var.github_org
      github_repo  = var.github_repo
      runner_name  = "gce-runner-${var.environment}"
    })
  }

  service_account {
    email  = var.service_account_email
    scopes = ["cloud-platform"]
  }

  scheduling {
    automatic_restart   = false
    on_host_maintenance = "TERMINATE"
    preemptible         = true
  }

  lifecycle {
    create_before_destroy = true
  }
}
