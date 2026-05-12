#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/home/deploy/game-video-tool}"
DATA_DIR="${DATA_DIR:-/home/deploy/game-video-data}"
BACKUP_DIR="${BACKUP_DIR:-/home/deploy/game-video-backups}"
LOG_FILE="${LOG_FILE:-${APP_DIR}/app.log}"
DIST_DIR="${DIST_DIR:-${APP_DIR}/react-ui/dist}"
RECENT_LINES="${RECENT_LINES:-20000}"

print_section() {
  printf '\n## %s\n' "$1"
}

human_size() {
  local path="$1"
  if [[ -e "${path}" ]]; then
    du -sh "${path}" 2>/dev/null | awk '{print $1}'
  else
    printf 'missing'
  fi
}

file_bytes() {
  local path="$1"
  if [[ -f "${path}" ]]; then
    stat -c%s "${path}" 2>/dev/null || stat -f%z "${path}" 2>/dev/null || printf 'unknown'
  else
    printf 'missing'
  fi
}

mask_secret() {
  local value="$1"
  value="${value//\"/}"
  value="${value//\'/}"
  value="${value// /}"

  if [[ -z "${value}" ]]; then
    printf 'empty'
    return
  fi

  local tail_len=4
  if [[ "${#value}" -lt "${tail_len}" ]]; then
    tail_len="${#value}"
  fi
  printf '...%s' "${value: -tail_len}"
}

count_log_pattern() {
  local pattern="$1"
  if [[ -f "${LOG_FILE}" ]]; then
    tail -n "${RECENT_LINES}" "${LOG_FILE}" 2>/dev/null | grep -Eic "${pattern}" || true
  else
    printf '0'
  fi
}

print_section "Inspection Context"
printf 'time: %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')"
printf 'host: %s\n' "$(hostname)"
printf 'app_dir: %s\n' "${APP_DIR}"
printf 'data_dir: %s\n' "${DATA_DIR}"
printf 'backup_dir: %s\n' "${BACKUP_DIR}"
printf 'log_file: %s\n' "${LOG_FILE}"
printf 'dist_dir: %s\n' "${DIST_DIR}"
printf 'recent_log_lines: %s\n' "${RECENT_LINES}"

print_section "Disk"
df -h "${APP_DIR}" "${DATA_DIR}" "${BACKUP_DIR}" 2>/dev/null || df -h

print_section "Directory Sizes"
printf '%-12s %s\n' "app" "$(human_size "${APP_DIR}")"
printf '%-12s %s\n' "data" "$(human_size "${DATA_DIR}")"
printf '%-12s %s\n' "backup" "$(human_size "${BACKUP_DIR}")"
printf '%-12s %s\n' "dist" "$(human_size "${DIST_DIR}")"

print_section "Application Log"
printf 'size_bytes: %s\n' "$(file_bytes "${LOG_FILE}")"
if [[ -f "${LOG_FILE}" ]]; then
  printf 'mtime: %s\n' "$(stat -c%y "${LOG_FILE}" 2>/dev/null || stat -f '%Sm' "${LOG_FILE}" 2>/dev/null || printf 'unknown')"
fi
printf 'recent_error_count: %s\n' "$(count_log_pattern '(^|[[:space:]])(ERROR|CRITICAL|FATAL)(:|[[:space:]])|Traceback|Exception')"
printf 'recent_http_429_count: %s\n' "$(count_log_pattern 'HTTP/[0-9.]+" 429')"
printf 'recent_gemini_429_count: %s\n' "$(count_log_pattern 'RESOURCE_EXHAUSTED|Gemini key hit|排队超时')"
printf 'recent_http_5xx_count: %s\n' "$(count_log_pattern 'HTTP/[0-9.]+" 5[0-9][0-9]')"

print_section "Gemini Keys"
key_sources=()
for candidate in "${APP_DIR}/.env" "${APP_DIR}/.env.production" "${APP_DIR}/server/.env"; do
  [[ -f "${candidate}" ]] && key_sources+=("${candidate}")
done
settings_file="${DATA_DIR}/settings.json"

key_count=0
if [[ "${#key_sources[@]}" -gt 0 ]]; then
  for source in "${key_sources[@]}"; do
    while IFS= read -r line; do
      [[ "${line}" =~ ^[[:space:]]*# ]] && continue
      [[ "${line}" != *GEMINI*KEY* && "${line}" != *GOOGLE*API*KEY* ]] && continue
      name="${line%%=*}"
      values="${line#*=}"
      IFS=',' read -r -a parts <<< "${values}"
      for part in "${parts[@]}"; do
        [[ -z "${part// /}" ]] && continue
        key_count=$((key_count + 1))
        printf '%s key_%02d_tail: %s\n' "$(basename "${source}")" "${key_count}" "$(mask_secret "${part}")"
      done
    done < "${source}"
  done
else
  printf 'env_files: none found\n'
fi
if [[ -f "${settings_file}" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    while IFS= read -r tail; do
      [[ -z "${tail}" ]] && continue
      key_count=$((key_count + 1))
      printf 'settings.json key_%02d_tail: %s\n' "${key_count}" "$(mask_secret "${tail}")"
    done < <(python3 - "${settings_file}" <<'PY'
import json
import sys

path = sys.argv[1]
names = ("gemini_api_keys", "gemini_api_key", "game_gemini_api_keys", "game_gemini_api_key")
try:
    data = json.load(open(path, encoding="utf-8"))
except Exception:
    data = {}

seen = set()
for name in names:
    value = data.get(name, "")
    text = ",".join(value) if isinstance(value, list) else str(value or "")
    for part in text.replace("\n", ",").replace(";", ",").split(","):
        key = part.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        print(key[-4:])
PY
)
  else
    printf 'settings_json: present, python3 unavailable for safe key counting\n'
  fi
else
  printf 'settings_json: missing\n'
fi
printf 'gemini_key_count: %s\n' "${key_count}"

print_section "Frontend Dist"
if [[ -d "${DIST_DIR}" ]]; then
  printf 'index_html: %s\n' "$([[ -f "${DIST_DIR}/index.html" ]] && echo present || echo missing)"
  printf 'asset_files: %s\n' "$(find "${DIST_DIR}" -type f \( -name '*.js' -o -name '*.css' -o -name '*.svg' -o -name '*.png' -o -name '*.webp' \) 2>/dev/null | wc -l | tr -d ' ')"
  find "${DIST_DIR}" -maxdepth 2 -type f 2>/dev/null | sed "s#^${DIST_DIR}/##" | sort | head -n 20
else
  printf 'dist directory missing\n'
fi

print_section "Processes"
if ! ps_output="$(ps aux 2>/dev/null)"; then
  printf 'process listing unavailable\n'
else
  printf '%s\n' "${ps_output}" \
    | grep -E 'game-video-tool|server/main.py|uvicorn|gunicorn|vite|node_modules/vite' \
    | grep -v -E 'grep|production-inspect.sh' || true
fi

print_section "Readonly Result"
printf 'inspection_complete: true\n'
printf 'mutations_performed: false\n'
