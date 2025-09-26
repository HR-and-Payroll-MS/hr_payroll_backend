#!/usr/bin/env bash
set -euo pipefail

# Pull images from Docker Hub and retag to local compose names
# Usage:
#   scripts/linux/pull-retag.sh <DOCKERHUB_NAMESPACE> [TAG]

if [[ $# -lt 1 ]]; then
  echo "Missing DOCKERHUB_NAMESPACE (your Docker Hub username or org)"
  echo "Usage: $0 DOCKERHUB_NAMESPACE [TAG]"
  exit 1
fi

NAMESPACE="$1"
TAG="${2:-latest}"
REPO_PREFIX="hr-payroll"
services=(django postgres traefik nginx celeryworker celerybeat flower)

# Validate namespace format (must not contain '/')
if [[ "$NAMESPACE" == *"/"* ]]; then
  echo "Error: NAMESPACE should be your Docker Hub username or org only (no slash)."
  echo "       Given: '$NAMESPACE' -> would create invalid path '${NAMESPACE}/${REPO_PREFIX}-<svc>'"
  echo "       Example usage: $0 yourname v1.0.0"
  exit 1
fi

for svc in "${services[@]}"; do
  remote_img="${NAMESPACE}/${REPO_PREFIX}-${svc}:${TAG}"
  local_img="hr_payroll_production_${svc}"
  echo "Pulling ${remote_img}"
  docker pull "${remote_img}"
  echo "Retagging ${remote_img} as ${local_img}"
  docker tag "${remote_img}" "${local_img}"
done

echo "Done. You can now run: docker compose -f docker-compose.production.yml up -d"
