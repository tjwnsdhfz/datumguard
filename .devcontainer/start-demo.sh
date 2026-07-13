#!/usr/bin/env bash
set -euo pipefail

if [[ "${CODESPACES:-false}" = "true" ]]; then
  forwarding_domain="${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-app.github.dev}"
  web_origin="https://${CODESPACE_NAME}-3000.${forwarding_domain}"
  api_origin="${web_origin}"
  export DATUMGUARD_LOCAL_API_PROXY=true
else
  api_origin="http://127.0.0.1:8000"
  web_origin="http://localhost:3000"
fi

export NEXT_PUBLIC_DATUMGUARD_API_URL="${NEXT_PUBLIC_DATUMGUARD_API_URL:-${api_origin}}"
export DATUMGUARD_CORS_ORIGINS="${DATUMGUARD_CORS_ORIGINS:-${web_origin}}"

uv run --frozen datumguard-api &
api_pid=$!
npm --prefix web run dev &
web_pid=$!

cleanup() {
  kill "${api_pid}" "${web_pid}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

wait -n "${api_pid}" "${web_pid}"
