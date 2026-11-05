#!/usr/bin/env bash
# Fails if versions pinned in more than one place have drifted apart. Dependabot updates
# the Dockerfile and docker-compose.yml but not the CI workflow, so this catches its PRs
# until the workflow is updated in the same PR.
#   - uv: CI's UV_VERSION must match the uv image tag in backend/Dockerfile
#   - Postgres: CI's service image must match backend/docker-compose.yml (tag and digest)
set -euo pipefail

root="${1:-.}"
workflow="$root/.github/workflows/backend-ci.yml"
dockerfile="$root/backend/Dockerfile"
compose="$root/backend/docker-compose.yml"
status=0

ci_uv=$(grep -oE 'UV_VERSION: "[0-9][0-9.]*"' "$workflow" | grep -oE '[0-9][0-9.]*' || true)
docker_uv=$(grep -oE 'ghcr\.io/astral-sh/uv:[0-9][0-9.]*' "$dockerfile" | cut -d: -f2 || true)
if [[ -z "$ci_uv" || "$ci_uv" != "$docker_uv" ]]; then
  echo "uv mismatch: CI '${ci_uv:-missing}' vs Dockerfile '${docker_uv:-missing}'"
  status=1
fi

pg_pattern='postgres:[0-9][^@" ]*@sha256:[0-9a-f]{64}'
ci_pg=$(grep -oE "$pg_pattern" "$workflow" || true)
compose_pg=$(grep -oE "$pg_pattern" "$compose" || true)
if [[ -z "$ci_pg" || "$ci_pg" != "$compose_pg" ]]; then
  echo "Postgres mismatch: CI '${ci_pg:-missing}' vs compose '${compose_pg:-missing}'"
  status=1
fi

if [[ $status -eq 0 ]]; then
  echo "Pinned versions match: uv $ci_uv, ${ci_pg%%@*}"
fi
exit "$status"
