#!/usr/bin/env bash
#
# Cloud Agent install phase for DEMIS Query Assistant (DQA).
#
# Idempotent repository bootstrap that runs after checkout. It installs the
# system packages the default-branch app needs (PostgreSQL, pgvector, Python
# build tooling) and project dependencies when their manifests exist.
#
# It must terminate. Dev servers and the PostgreSQL cluster are started by
# scripts/cloud-agent-start.sh, not here.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

log() { printf '\n[install] %s\n' "$*"; }

# ---------------------------------------------------------------------------
# System dependencies (idempotent). Captured by the environment snapshot so a
# booted agent already has them; a snapshot-less run installs them on demand.
# ---------------------------------------------------------------------------
ensure_system_packages() {
  local base_packages=(
    postgresql
    postgresql-contrib
    libpq-dev
    python3-venv
    python3-dev
    build-essential
  )
  local missing=()
  local pkg
  for pkg in "${base_packages[@]}"; do
    if ! dpkg -s "$pkg" >/dev/null 2>&1; then
      missing+=("$pkg")
    fi
  done
  if ((${#missing[@]})); then
    log "Installing system packages: ${missing[*]}"
    sudo apt-get update -qq
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "${missing[@]}"
  else
    log "Base system packages already present."
  fi

  if ! command -v pg_lsclusters >/dev/null 2>&1; then
    log "PostgreSQL cluster tools are missing after package install."
    exit 1
  fi

  local pg_ver vector_pkg
  pg_ver="$(pg_lsclusters -h | awk 'NR==1 {print $1}')"
  pg_ver="${pg_ver:-16}"
  vector_pkg="postgresql-${pg_ver}-pgvector"
  if dpkg -s "$vector_pkg" >/dev/null 2>&1; then
    log "${vector_pkg} already present."
    return
  fi
  log "Installing ${vector_pkg} (Data Discovery embeddings)."
  sudo apt-get update -qq
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "$vector_pkg"
}

# ---------------------------------------------------------------------------
# Local development .env (never committed) derived from the committed template.
# The generated file enables the documented local dev_headers provider so the
# UI can call the API. It is gitignored and must not be copied to production.
# ---------------------------------------------------------------------------
ensure_dev_env_file() {
  if [[ -f .env ]]; then
    log ".env already exists; leaving it untouched."
    return
  fi
  if [[ ! -f .env.example ]]; then
    return
  fi
  log "Creating development .env from .env.example (local dev_headers, password dqa)."
  sed \
    -e 's/^DQA_DB_HOST=.*/DQA_DB_HOST=localhost/' \
    -e 's/^DQA_DB_PORT=.*/DQA_DB_PORT=5432/' \
    -e 's/^DQA_DB_NAME=.*/DQA_DB_NAME=dqa/' \
    -e 's/^DQA_DB_USER=.*/DQA_DB_USER=dqa/' \
    -e 's/^DQA_DB_PASSWORD=.*/DQA_DB_PASSWORD=dqa/' \
    -e 's/^DQA_AUTH_PROVIDER=.*/DQA_AUTH_PROVIDER=dev_headers/' \
    .env.example > .env
  if ! grep -q '^DQA_AUTH_PROVIDER=' .env; then
    printf '\n# Local Cloud Agent only. Never use dev_headers in production.\nDQA_AUTH_PROVIDER=dev_headers\n' >> .env
  fi
}

# ---------------------------------------------------------------------------
# Backend dependencies (guarded until a manifest exists).
# ---------------------------------------------------------------------------
install_backend() {
  if [[ ! -d backend ]]; then
    return
  fi
  if [[ -f backend/requirements.txt || -f backend/pyproject.toml ]]; then
    log "Setting up backend Python virtualenv (backend/.venv)."
    python3 -m venv backend/.venv
    # shellcheck disable=SC1091
    source backend/.venv/bin/activate
    python -m pip install --upgrade pip wheel
    # Install from backend/ so requirements.txt editable paths (.-relative) resolve.
    pushd backend >/dev/null
    if [[ -f requirements.txt ]]; then
      log "Installing backend requirements.txt (delegates to pyproject.toml)."
      python -m pip install -r requirements.txt
    elif [[ -f pyproject.toml ]]; then
      log "Installing backend project (editable, with dev extras)."
      python -m pip install -e ".[dev]"
    fi
    popd >/dev/null
    deactivate
  else
    log "No backend dependency manifest yet (requirements.txt / pyproject.toml); skipping."
  fi
}

# ---------------------------------------------------------------------------
# Frontend dependencies (guarded until a manifest exists).
# ---------------------------------------------------------------------------
install_frontend() {
  if [[ ! -f frontend/package.json ]]; then
    log "No frontend/package.json yet; skipping frontend install."
    return
  fi
  if ! command -v npm >/dev/null 2>&1; then
    log "npm is required to install the frontend but was not found on PATH."
    exit 1
  fi
  pushd frontend >/dev/null
  if [[ -f pnpm-lock.yaml ]] && command -v pnpm >/dev/null 2>&1; then
    log "Installing frontend dependencies with pnpm (frozen lockfile)."
    pnpm install --frozen-lockfile
  elif [[ -f package-lock.json ]]; then
    log "Installing frontend dependencies with npm ci."
    npm ci
  else
    log "Installing frontend dependencies with npm install."
    npm install
  fi
  popd >/dev/null
}

ensure_system_packages
ensure_dev_env_file
install_backend
install_frontend

log "Install phase complete."
