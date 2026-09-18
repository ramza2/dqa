#!/usr/bin/env bash
#
# Cloud Agent install phase for DEMIS Query Assistant (DQA).
#
# Idempotent repository bootstrap that runs after the source tree is checked
# out. It provisions the toolchain required by the planned stack (FastAPI /
# Python 3.11+ / PostgreSQL backend, React / TypeScript / Vite frontend) and
# installs project dependencies when their manifests exist.
#
# This repository is still in its bootstrap phase: backend/ and frontend/ do
# not yet contain dependency manifests. Every project-dependency step is guarded
# so this script succeeds today and automatically starts installing real
# dependencies once the feature PRs land.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

log() { printf '\n[install] %s\n' "$*"; }

# ---------------------------------------------------------------------------
# System dependencies (idempotent). Captured by the environment snapshot so a
# booted agent already has them; a snapshot-less run installs them on demand.
# ---------------------------------------------------------------------------
ensure_system_packages() {
  if command -v pg_ctlcluster >/dev/null 2>&1 && command -v pg_config >/dev/null 2>&1; then
    log "System packages already present; skipping apt install."
    return
  fi
  log "Installing system packages (PostgreSQL, Python build tooling)..."
  sudo apt-get update -qq
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    postgresql postgresql-contrib libpq-dev \
    python3-venv python3-dev build-essential
}

# ---------------------------------------------------------------------------
# Local development .env (never committed) derived from the committed template.
# ---------------------------------------------------------------------------
ensure_dev_env_file() {
  if [[ -f .env ]]; then
    log ".env already exists; leaving it untouched."
    return
  fi
  if [[ ! -f .env.example ]]; then
    return
  fi
  log "Creating development .env from .env.example."
  sed \
    -e 's/^DQA_DB_HOST=.*/DQA_DB_HOST=localhost/' \
    -e 's/^DQA_DB_PORT=.*/DQA_DB_PORT=5432/' \
    -e 's/^DQA_DB_NAME=.*/DQA_DB_NAME=dqa/' \
    -e 's/^DQA_DB_USER=.*/DQA_DB_USER=dqa/' \
    -e 's/^DQA_DB_PASSWORD=.*/DQA_DB_PASSWORD=dqa/' \
    .env.example > .env
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
  pushd frontend >/dev/null
  if [[ -f pnpm-lock.yaml ]]; then
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
