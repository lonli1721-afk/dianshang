#!/usr/bin/env bash
set -Eeuo pipefail

DATA_DIR="${GAME_VIDEO_DATA_DIR:-/home/deploy/game-video-data}"
BACKUP_DIR="${GAME_VIDEO_BACKUP_DIR:-/home/deploy/game-video-backups}"
WARN_PERCENT="${GAME_VIDEO_DISK_WARN_PERCENT:-70}"
BLOCK_PERCENT="${GAME_VIDEO_DISK_BLOCK_PERCENT:-90}"
MIN_FREE_GB="${GAME_VIDEO_DISK_MIN_FREE_GB:-5}"

paths=("${DATA_DIR}" "${BACKUP_DIR}")
status=0

bytes_to_gb() {
  awk -v bytes="$1" 'BEGIN { printf "%.2f", bytes / 1024 / 1024 / 1024 }'
}

for path in "${paths[@]}"; do
  [[ -e "${path}" ]] || continue
  line="$(df -P "${path}" | awk 'NR==2 {print $2, $3, $4, $5, $6}')"
  read -r total_k used_k avail_k used_percent mount <<< "${line}"
  percent="${used_percent%%%}"
  free_bytes=$((avail_k * 1024))
  free_gb="$(bytes_to_gb "${free_bytes}")"
  printf 'path=%s mount=%s used=%s free_gb=%s\n' "${path}" "${mount}" "${used_percent}" "${free_gb}"

  if [[ "${percent}" -ge "${BLOCK_PERCENT}" ]]; then
    printf 'BLOCK disk usage %s >= %s on %s\n' "${used_percent}" "${BLOCK_PERCENT}%" >&2
    status=2
  elif [[ "${percent}" -ge "${WARN_PERCENT}" && "${status}" -lt 1 ]]; then
    printf 'WARN disk usage %s >= %s on %s\n' "${used_percent}" "${WARN_PERCENT}%" >&2
    status=1
  fi

  min_free_bytes="$(awk -v gb="${MIN_FREE_GB}" 'BEGIN { printf "%.0f", gb * 1024 * 1024 * 1024 }')"
  if [[ "${free_bytes}" -lt "${min_free_bytes}" ]]; then
    printf 'BLOCK free space %sGB < %sGB on %s\n' "${free_gb}" "${MIN_FREE_GB}" "${mount}" >&2
    status=2
  fi
done

exit "${status}"
