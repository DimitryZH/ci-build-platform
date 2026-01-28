terraform {
  backend "gcs" {
    bucket = "tf-state-ci-build-platform"
    prefix = "gce-runners"
  }
}
