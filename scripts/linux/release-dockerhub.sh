#!/usr/bin/env bash
set -euo pipefail

# Build, tag, and push all production images to Docker Hub (Linux/WSL)
# Usage:
#   scripts/linux/release-dockerhub.sh <DOCKERHUB_NAMESPACE> [TAG]
# Example:
#   scripts/linux/release-dockerhub.sh yourname v1.0.0

if [[ $# -lt 1 ]]; then
  echo "Missing DOCKERHUB_NAMESPACE (your Docker Hub username or org)"
  echo "Usage: $0 DOCKERHUB_NAMESPACE [TAG]"
  exit 1
fi

NAMESPACE="$1"
TAG="${2:-latest}"

REPO_PREFIX="hr-payroll"
COMPOSE_FILE="docker-compose.production.yml"

# Validate namespace format (Docker Hub requires exactly two segments: <namespace>/<repo>)
# The script constructs repos as: ${NAMESPACE}/${REPO_PREFIX}-${svc}:${TAG}
# So NAMESPACE must not contain '/'
if [[ "$NAMESPACE" == *"/"* ]]; then
  echo "Error: NAMESPACE should be your Docker Hub username or org only (no slash)."
  echo "       Given: '$NAMESPACE' -> would create invalid path '${NAMESPACE}/${REPO_PREFIX}-<svc>'"
  echo "       Example usage: $0 yourname v1.0.0"
  exit 1
fi

echo "Logging in to Docker Hub (skip if already logged in)..."
docker login || { echo "Docker login failed. Please login and re-run."; exit 1; }

echo "Building images defined in ${COMPOSE_FILE} ..."
docker compose -f "${COMPOSE_FILE}" build --pull

services=(django postgres traefik nginx celeryworker celerybeat flower)

for svc in "${services[@]}"; do
  local_img="hr_payroll_production_${svc}"
  remote_img="${NAMESPACE}/${REPO_PREFIX}-${svc}:${TAG}"
  echo "Tagging ${local_img} as ${remote_img}"
  docker image inspect "${local_img}" >/dev/null 2>&1 || { echo "Local image ${local_img} not found. Did the build succeed?"; exit 1; }
  docker tag "${local_img}" "${remote_img}"
  echo "Pushing ${remote_img}"
  docker push "${remote_img}"
done

echo "Done. Pushed tags under ${NAMESPACE} with tag ${TAG}."
