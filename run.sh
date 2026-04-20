#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_name="$(basename "${project_dir}")"
venv_dir="${HOME}/venv/${project_name}"

listen_host="${1:-${LISTEN_HOST:-0.0.0.0}}"
listen_port="${2:-${LISTEN_PORT:-8000}}"

if [ -f "${project_dir}/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "${project_dir}/.env"
  set +a
fi

export LISTEN_HOST="${listen_host}"
export LISTEN_PORT="${listen_port}"

if [ ! -x "${venv_dir}/bin/python" ]; then
  echo "ERROR: missing virtualenv at ${venv_dir}"
  echo "Run: ./install.sh"
  return 1 2>/dev/null || exit 1
fi

if [ -z "${UPSTREAM_BASE:-}" ]; then
  export UPSTREAM_BASE="https://api.openai.com/v1"
fi

if [ "${REQUIRE_PROXY_AUTH:-true}" = "true" ] && [ -z "${PROXY_API_TOKEN:-}" ]; then
  echo "ERROR: PROXY_API_TOKEN is empty while REQUIRE_PROXY_AUTH is enabled"
  return 1 2>/dev/null || exit 1
fi

cd "${project_dir}"

exec "${venv_dir}/bin/python" -m uvicorn \
  app:app \
  --host "${LISTEN_HOST}" \
  --port "${LISTEN_PORT}" \
  --proxy-headers \
  --forwarded-allow-ips='*'
