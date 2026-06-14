#!/usr/bin/env bash
# Create a consistent SQLite backup of the VeriAgent database while the API may be running.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${REPO_ROOT}/backend/.env"
DEFAULT_DB_PATH="/opt/veriagent/backend/data/veriagent.db"
BACKUP_DIR="/opt/veriagent/backups/sqlite"
RETENTION_COUNT=14

DB_PATH="${DEFAULT_DB_PATH}"

if [[ -f "${ENV_FILE}" ]]; then
  # shellcheck disable=SC1090
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

if ! command -v sqlite3 >/dev/null 2>&1; then
  echo "error: sqlite3 is required but not found in PATH" >&2
  exit 1
fi

if [[ ! -f "${DB_PATH}" ]]; then
  echo "error: database file not found: ${DB_PATH}" >&2
  exit 1
fi

mkdir -p "${BACKUP_DIR}"

timestamp="$(date -u +"%Y%m%dT%H%M%SZ")"
backup_base="${BACKUP_DIR}/veriagent-${timestamp}.db"
backup_gz="${backup_base}.gz"

echo "Backing up ${DB_PATH}"
echo "Destination: ${backup_gz}"

sqlite3 "${DB_PATH}" ".backup '${backup_base}'"
gzip -f "${backup_base}"

mapfile -t stale_backups < <(ls -1t "${BACKUP_DIR}"/veriagent-*.db.gz 2>/dev/null | tail -n +$((RETENTION_COUNT + 1)) || true)
if ((${#stale_backups[@]} > 0)); then
  echo "Removing ${#stale_backups[@]} backup(s) beyond retention of ${RETENTION_COUNT}"
  rm -f "${stale_backups[@]}"
fi

echo "Backup complete: ${backup_gz}"
ls -lh "${backup_gz}"
