#!/usr/bin/env bash
# Shared helpers for DQA on-prem Compose scripts.
# shellcheck shell=bash

set -euo pipefail

DQA_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DQA_COMPOSE_FILE="${DQA_COMPOSE_FILE:-${DQA_ROOT}/docker-compose.onprem.yml}"
DQA_ENV_FILE="${DQA_ENV_FILE:-${DQA_ROOT}/.env.onprem}"
DQA_COMPOSE_PROJECT_NAME="${DQA_COMPOSE_PROJECT_NAME:-dqa-onprem}"

dqa_require_cmd() {
  local cmd="$1"
  if ! command -v "${cmd}" >/dev/null 2>&1; then
    echo "error: required command not found: ${cmd}" >&2
    exit 1
  fi
}

dqa_require_env_file() {
  if [[ ! -f "${DQA_ENV_FILE}" ]]; then
    echo "error: missing ${DQA_ENV_FILE}" >&2
    echo "Copy .env.onprem.example to .env.onprem and set required values (including DQA_DB_PASSWORD)." >&2
    exit 1
  fi
}

# Ensure a key exists with a non-empty value. Never print the value.
dqa_require_env_key() {
  local key="$1"
  local line
  line="$(grep -E "^${key}=" "${DQA_ENV_FILE}" | tail -n 1 || true)"
  if [[ -z "${line}" ]]; then
    echo "error: required variable ${key} is missing from ${DQA_ENV_FILE}" >&2
    exit 1
  fi
  local value="${line#*=}"
  # Strip optional surrounding quotes without echoing secrets elsewhere.
  if [[ "${value}" == \"*\" && "${value}" == *\" ]]; then
    value="${value:1:-1}"
  elif [[ "${value}" == \'*\' && "${value}" == *\' ]]; then
    value="${value:1:-1}"
  fi
  if [[ -z "${value}" ]]; then
    echo "error: required variable ${key} is empty in ${DQA_ENV_FILE}" >&2
    exit 1
  fi
}

dqa_compose() {
  docker compose \
    -p "${DQA_COMPOSE_PROJECT_NAME}" \
    -f "${DQA_COMPOSE_FILE}" \
    --env-file "${DQA_ENV_FILE}" \
    "$@"
}

dqa_preflight() {
  dqa_require_cmd docker
  if ! docker compose version >/dev/null 2>&1; then
    echo "error: docker compose is required" >&2
    exit 1
  fi
  dqa_require_env_file
  dqa_require_env_key DQA_DB_PASSWORD
  dqa_require_env_key DQA_LAN_BIND_IP
}
