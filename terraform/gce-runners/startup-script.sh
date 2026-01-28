#!/bin/bash
set -e

echo "Installing dependencies..."
apt-get update -y
apt-get install -y curl jq docker.io

systemctl enable docker
systemctl start docker

RUNNER_VERSION="2.314.1"
mkdir -p /actions-runner
cd /actions-runner

echo "Downloading GitHub Actions Runner..."
curl -o actions-runner.tar.gz -L \
https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz

tar xzf actions-runner.tar.gz

echo "Requesting GitHub registration token..."
REG_TOKEN=$(curl -s -X POST \
  -H "Authorization: token ${github_token}" \
  https://api.github.com/repos/${github_owner}/${github_repo}/actions/runners/registration-token \
  | jq -r .token)

echo "Configuring runner..."
./config.sh --url https://github.com/${github_owner}/${github_repo} \
  --token $REG_TOKEN \
  --name gce-runner-$(hostname) \
  --labels gce,self-hosted \
  --unattended \
  --replace

echo "Starting runner..."
./run.sh

echo "Job finished — shutting down VM"
shutdown -h now

