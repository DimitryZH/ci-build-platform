terraform {
  backend "gcs" {
    bucket  = "ci-platform-tf-state"
    prefix  = "global"
  }
}

