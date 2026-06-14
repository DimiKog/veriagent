#!/usr/bin/env bash
# Restore VeriAgent SQLite from a gzipped backup created by backup_sqlite.sh.
set -euo pipefail

SERVICE_NAME="${VERIAGENT_SERVICE_NAME:-veriagent}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${REPO_ROOT}/backend/.env"
DEFAULT_DB_PATH="/opt/veriagent/backend/data/veriagent.db"
BACKUP_DIR="/opt/veriagent/backups/sqlite"

usage() {
  cat <<EOF
Usage: $(basename "$0") <path-to-backup.db.gz>

Restore the VeriAgent SQLite database from a gzipped backup file.
The service is stopped during restore; the current database is copied to
${BACKUP_DIR}/emergency-<timestamp>-veriagent.db before overwrite.

Example:
  sudo $(basename "$0") /opt/veriagent/backups/sqlite/veriagent-20260614T120000Z.db.gz
EOF
}

if [[ $# -ne 1 ]]; then
  usage >&2
  exit 1
fi

BACKUP_FILE="$1"

if [[ ! -f "${BACKUP_FILE}" ]]; then
  echo "error: backup file not found: ${BACKUP_FILE}" >&2
  exit 1
fi

if [[ "${BACKUP_FILE}" != *.gz ]]; then
  echo "error: backup file must be a .gz file produced by backup_sqlite.sh" >&2
  exit 1
fi

DB_PATH="${DEFAULT_DB_PATH}"

if [[ -f "${ENV_FILE}" ]]; then
  line="$(grep -E '^[[:space:]]*(export[[:space:]]+)?VERIAGENT_DB_PATH=' "${ENV_FILE}" | tail -n1 || true)"
  if [[ -n "${line}" ]]; then
    value="${line#*=}"
    value="${value#export }"
    value="${value#"${value%%[![:space:]]*}"}"
    value="${value%"${value##*[![:space:]]}"}"
    value="${value%\"}"
    value="${value#\"}"
    value="${value%\'}"
    value="${value#\'}"
    if [[ -n "${value}" ]]; then
      DB_PATH="${value}"
    fi
  fi
fi

if ! command -v systemctl >/dev/null 2>&1; then
  echo "error: systemctl is required but not found in PATH" >&2
  exit 1
fi

mkdir -p "${BACKUP_DIR}"
mkdir -p "$(dirname "${DB_PATH}")"

timestamp="$(date -u +"%Y%m%dT%H%M%SZ")"
emergency_backup="${BACKUP_DIR}/emergency-${timestamp}-veriagent.db"

echo "Stopping ${SERVICE_NAME} service"
systemctl stop "${SERVICE_NAME}"

if [[ -f "${DB_PATH}" ]]; then
  echo "Saving current database to ${emergency_backup}"
  cp -a "${DB_PATH}" "${emergency_backup}"
else
  echo "warning: no existing database at ${DB_PATH}; continuing with restore" >&2
fi

echo "Restoring from ${BACKUP_FILE}"
gunzip -c "${BACKUP_FILE}" > "${DB_PATH}.restore.tmp"
mv "${DB_PATH}.restore.tmp" "${DB_PATH}"

echo "Starting ${SERVICE_NAME} service"
systemctl start "${SERVICE_NAME}"

if systemctl is-active --quiet "${SERVICE_NAME}"; then
  echo "Restore complete. Service is active."
else
  echo "error: restore finished but ${SERVICE_NAME} is not active; check journalctl -u ${SERVICE_NAME}" >&2
  exit 1
fi

echo "Restored database: ${DB_PATH}"
if [[ -f "${emergency_backup}" ]]; then
  echo "Emergency copy: ${emergency_backup}"
fi
