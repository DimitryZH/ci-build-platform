output "runner_instance_name" {
  description = "Name of the GCE runner instance"
  value       = google_compute_instance.runner.name
}

output "runner_instance_zone" {
  description = "Zone of the GCE runner instance"
  value       = google_compute_instance.runner.zone
}

output "runner_instance_ip" {
  description = "External IP of the runner instance"
  value       = google_compute_instance.runner.network_interface[0].access_config[0].nat_ip
}
