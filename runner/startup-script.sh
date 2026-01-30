#!/bin/bash
set -euo pipefail

# ---- CONFIG ----
RUNNER_VERSION="2.317.0"
RUNNER_DIR="/opt/github-runner"

GITHUB_TOKEN="${github_token}"
GITHUB_ORG="${github_org}"
GITHUB_REPO="${github_repo}"
RUNNER_NAME="${runner_name}"

# ---- SYSTEM SETUP ----
apt-get update
apt-get install -y \
  curl \
  jq \
  ca-certificates \
  git \
  docker.io

systemctl start docker
systemctl enable docker

usermod -aG docker ubuntu

# ---- DOWNLOAD RUNNER ----
mkdir -p ${RUNNER_DIR}
cd ${RUNNER_DIR}

curl -L -o actions-runner.tar.gz \
  https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz

tar xzf actions-runner.tar.gz
chown -R ubuntu:ubuntu ${RUNNER_DIR}

# ---- GET REGISTRATION TOKEN ----
REG_TOKEN=$(curl -s -X POST \
  -H "Authorization: token ${GITHUB_TOKEN}" \
  -H "Accept: application/vnd.github+json" \
  https://api.github.com/repos/${GITHUB_ORG}/${GITHUB_REPO}/actions/runners/registration-token \
  | jq -r .token)

# ---- CONFIGURE RUNNER ----
sudo -u ubuntu ./config.sh \
  --url https://github.com/${GITHUB_ORG}/${GITHUB_REPO} \
  --token ${REG_TOKEN} \
  --name ${RUNNER_NAME} \
  --labels gce,ephemeral \
  --unattended \
  --ephemeral

# ---- RUN ----
sudo -u ubuntu ./run.sh

# ---- SELF-DESTRUCT ----
shutdown -h now

