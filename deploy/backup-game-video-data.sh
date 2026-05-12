#!/usr/bin/env bash
set -Eeuo pipefail

DATA_DIR="${GAME_VIDEO_DATA_DIR:-/home/deploy/game-video-data}"
BACKUP_ROOT="${GAME_VIDEO_BACKUP_DIR:-/home/deploy/game-video-backups}"
RETENTION_DAYS="${GAME_VIDEO_BACKUP_RETENTION_DAYS:-14}"
RETENTION_COUNT="${GAME_VIDEO_BACKUP_RETENTION_COUNT:-3}"

timestamp="$(date +%Y%m%d-%H%M%S)"
archive_name="game-video-data-${timestamp}.tar.gz"
archive_path="${BACKUP_ROOT}/${archive_name}"
log_path="${BACKUP_ROOT}/backup.log"

if [[ ! -d "${DATA_DIR}" ]]; then
  echo "Data directory not found: ${DATA_DIR}" >&2
  exit 1
fi

mkdir -p "${BACKUP_ROOT}"
work_dir="$(mktemp -d "${BACKUP_ROOT}/.work-${timestamp}-XXXXXX")"
snapshot_dir="${work_dir}/game-video-data"
old_backup_list="${work_dir}/old-backups.list"

cleanup() {
  rm -rf "${work_dir}"
}
trap cleanup EXIT

mkdir -p "${snapshot_dir}"

while IFS= read -r -d '' source_path; do
  rel_path="${source_path#"${DATA_DIR}/"}"
  [[ "${rel_path}" == "${source_path}" ]] && continue
  target_path="${snapshot_dir}/${rel_path}"

  if [[ -d "${source_path}" ]]; then
    mkdir -p "${target_path}"
  elif [[ -L "${source_path}" ]]; then
    mkdir -p "$(dirname "${target_path}")"
    cp -P "${source_path}" "${target_path}"
  elif [[ -f "${source_path}" ]]; then
    mkdir -p "$(dirname "${target_path}")"
    ln "${source_path}" "${target_path}" 2>/dev/null || cp -p "${source_path}" "${target_path}"
  fi
done < <(find "${DATA_DIR}" \
  \( -type f -o -type d -o -type l \) \
  ! -name '*.db' \
  ! -name '*.db-wal' \
  ! -name '*.db-shm' \
  ! -name '*.db-journal' \
  -print0)

while IFS= read -r -d '' db_path; do
  rel_path="${db_path#"${DATA_DIR}/"}"
  target_path="${snapshot_dir}/${rel_path}"
  mkdir -p "$(dirname "${target_path}")"
  sqlite3 "${db_path}" ".backup '${target_path}'"
done < <(find "${DATA_DIR}" -type f -name '*.db' -print0)

tar -C "${work_dir}" -czf "${archive_path}.tmp" game-video-data
mv "${archive_path}.tmp" "${archive_path}"

find "${BACKUP_ROOT}" -maxdepth 1 -type f -name 'game-video-data-*.tar.gz' -mtime +"${RETENTION_DAYS}" -delete
backup_count="$(find "${BACKUP_ROOT}" -maxdepth 1 -type f -name 'game-video-data-*.tar.gz' | wc -l | tr -d ' ')"
if [[ "${backup_count}" -gt "${RETENTION_COUNT}" ]]; then
  find "${BACKUP_ROOT}" -maxdepth 1 -type f -name 'game-video-data-*.tar.gz' -print0 \
    | xargs -0 ls -t \
    | tail -n +"$((RETENTION_COUNT + 1))" > "${old_backup_list}"
  while IFS= read -r old_backup; do
    [[ -n "${old_backup}" ]] && rm -f -- "${old_backup}"
  done < "${old_backup_list}"
fi

{
  printf '%s created %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "${archive_path}"
  ls -lh "${archive_path}"
} >> "${log_path}"

echo "${archive_path}"
