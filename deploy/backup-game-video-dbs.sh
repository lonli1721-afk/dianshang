#!/usr/bin/env bash
set -Eeuo pipefail

DATA_DIR="${GAME_VIDEO_DATA_DIR:-/home/deploy/game-video-data}"
BACKUP_ROOT="${GAME_VIDEO_BACKUP_DIR:-/home/deploy/game-video-backups}"
RETENTION_DAYS="${GAME_VIDEO_DB_BACKUP_RETENTION_DAYS:-7}"
RETENTION_COUNT="${GAME_VIDEO_DB_BACKUP_RETENTION_COUNT:-24}"

timestamp="$(date +%Y%m%d-%H%M%S)"
archive_name="game-video-dbs-${timestamp}.tar.gz"
archive_path="${BACKUP_ROOT}/${archive_name}"
log_path="${BACKUP_ROOT}/db-backup.log"
work_dir=""

cleanup() {
  if [[ -n "${work_dir}" && -d "${work_dir}" ]]; then
    rm -rf "${work_dir}"
  fi
}
trap cleanup EXIT

fail() {
  printf 'FAILED\nreason: %s\n' "$1" >&2
  exit 1
}

[[ -d "${DATA_DIR}" ]] || fail "data directory not found: ${DATA_DIR}"
command -v sqlite3 >/dev/null 2>&1 || fail "sqlite3 not found"

mkdir -p "${BACKUP_ROOT}"
work_dir="$(mktemp -d "${BACKUP_ROOT}/.db-work-${timestamp}-XXXXXX")"
snapshot_dir="${work_dir}/game-video-dbs"
mkdir -p "${snapshot_dir}"

if [[ -f "${DATA_DIR}/settings.json" ]]; then
  cp -p "${DATA_DIR}/settings.json" "${snapshot_dir}/settings.json"
fi

while IFS= read -r -d '' db_path; do
  rel_path="${db_path#"${DATA_DIR}/"}"
  target_path="${snapshot_dir}/${rel_path}"
  mkdir -p "$(dirname "${target_path}")"
  sqlite3 "${db_path}" ".backup '${target_path}'"
done < <(find "${DATA_DIR}" -type f -name '*.db' \
  ! -path "${DATA_DIR}/cloud-dbs/*" \
  ! -path "${DATA_DIR}/backups/*" \
  -print0)

tar -C "${work_dir}" -czf "${archive_path}.tmp" game-video-dbs
mv "${archive_path}.tmp" "${archive_path}"

find "${BACKUP_ROOT}" -maxdepth 1 -type f -name 'game-video-dbs-*.tar.gz' -mtime +"${RETENTION_DAYS}" -delete
backup_count="$(find "${BACKUP_ROOT}" -maxdepth 1 -type f -name 'game-video-dbs-*.tar.gz' | wc -l | tr -d ' ')"
if [[ "${backup_count}" -gt "${RETENTION_COUNT}" ]]; then
  while IFS= read -r old_backup; do
    [[ -n "${old_backup}" ]] && rm -f -- "${old_backup}"
  done < <(
    find "${BACKUP_ROOT}" -maxdepth 1 -type f -name 'game-video-dbs-*.tar.gz' -print0 \
      | xargs -0 ls -t \
      | tail -n +"$((RETENTION_COUNT + 1))"
  )
fi

{
  printf '%s created %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "${archive_path}"
  ls -lh "${archive_path}"
} >> "${log_path}"

echo "${archive_path}"
