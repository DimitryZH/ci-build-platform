#!/bin/bash
set -euo pipefail

GITHUB_OWNER="${github_owner}"
GITHUB_REPO="${github_repo}"
GITHUB_TOKEN="${github_token}"

RUNNER_NAME="$(hostname)"
RUNNER_VERSION="2.314.1"
RUNNER_DIR="/runner"

apt-get update -y
apt-get install -y curl jq git docker.io

mkdir -p $RUNNER_DIR
cd $RUNNER_DIR

curl -o actions-runner.tar.gz -L \
https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz

tar xzf actions-runner.tar.gz

REG_TOKEN=$(curl -s -X POST \
  -H "Authorization: token ${GITHUB_TOKEN}" \
  -H "Accept: application/vnd.github+json" \
  https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/actions/runners/registration-token \
  | jq -r .token)

./config.sh --url https://github.com/${GITHUB_OWNER}/${GITHUB_REPO} \
 --token ${REG_TOKEN} \
 --name ${RUNNER_NAME} \
 --unattended \
 --replace

./run.sh &

RUNNER_PID=$!
wait $RUNNER_PID

REMOVE_TOKEN=$(curl -s -X POST \
  -H "Authorization: token ${GITHUB_TOKEN}" \
  -H "Accept: application/vnd.github+json" \
  https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/actions/runners/remove-token \
  | jq -r .token)

./config.sh remove --token ${REMOVE_TOKEN}

shutdown -h now
