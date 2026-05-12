#!/usr/bin/env bash
set -Eeuo pipefail

NEW_DIST="${1:-}"
APP_DIR="${APP_DIR:-/home/deploy/game-video-tool}"
BACKUP_ROOT="${BACKUP_DIR:-/home/deploy/game-video-backups}"
RELEASE_ID="${RELEASE_ID:-frontend-r1-$(date +%Y%m%d-%H%M%S)}"
TARGET_DIST="${DIST_DIR:-${APP_DIR}/react-ui/dist}"
BACKUP_DIR="${FRONTEND_BACKUP_DIR:-${BACKUP_ROOT}/${RELEASE_ID}}"
PRESERVE_OLD_ASSETS="${PRESERVE_OLD_ASSETS:-1}"
WORK_DIR=""
OLD_DIST=""

fail() {
  printf 'FAILED\nreason: %s\n' "$1" >&2
  exit 1
}

cleanup() {
  if [[ -n "${WORK_DIR}" && -d "${WORK_DIR}" ]]; then
    rm -rf "${WORK_DIR}"
  fi
}
trap cleanup EXIT

[[ -n "${NEW_DIST}" ]] || fail "usage: deploy/install-frontend-dist.sh /path/to/new/react-ui/dist"
[[ -d "${NEW_DIST}" ]] || fail "new dist directory not found: ${NEW_DIST}"
[[ -f "${NEW_DIST}/index.html" ]] || fail "new dist index.html not found: ${NEW_DIST}/index.html"
[[ "${TARGET_DIST}" == */react-ui/dist ]] || fail "refusing unsafe TARGET_DIST: ${TARGET_DIST}"
[[ -d "${APP_DIR}" ]] || fail "app directory not found: ${APP_DIR}"

mkdir -p "${BACKUP_DIR}"
if [[ -d "${TARGET_DIST}" ]]; then
  rm -rf "${BACKUP_DIR}/dist-before"
  cp -a "${TARGET_DIST}" "${BACKUP_DIR}/dist-before"
fi

WORK_DIR="$(mktemp -d "${APP_DIR}/.frontend-dist.XXXXXX")"
mkdir -p "${WORK_DIR}/dist"
cp -a "${NEW_DIST}/." "${WORK_DIR}/dist/"
mkdir -p "${WORK_DIR}/dist/assets"

preserved_count=0
if [[ "${PRESERVE_OLD_ASSETS}" != "0" && -d "${TARGET_DIST}/assets" ]]; then
  while IFS= read -r asset; do
    name="$(basename "${asset}")"
    if [[ ! -e "${WORK_DIR}/dist/assets/${name}" ]]; then
      cp "${asset}" "${WORK_DIR}/dist/assets/${name}"
      preserved_count=$((preserved_count + 1))
    fi
  done < <(find "${TARGET_DIST}/assets" -maxdepth 1 -type f \( -name '*.js' -o -name '*.css' \) | sort)
fi

find "${WORK_DIR}/dist" -name '._*' -delete

missing_assets=()
while IFS= read -r asset_path; do
  [[ -f "${WORK_DIR}/dist/${asset_path}" ]] || missing_assets+=("${asset_path}")
done < <(grep -Eo "assets/[^\"' ]+\\.(js|css)" "${WORK_DIR}/dist/index.html" | sort -u)

if [[ "${#missing_assets[@]}" -gt 0 ]]; then
  printf 'missing assets referenced by index.html:\n' >&2
  printf '  %s\n' "${missing_assets[@]}" >&2
  fail "new dist has missing referenced assets"
fi

OLD_DIST="${TARGET_DIST}.old-${RELEASE_ID}"
rm -rf "${OLD_DIST}"
if [[ -d "${TARGET_DIST}" ]]; then
  mv "${TARGET_DIST}" "${OLD_DIST}"
fi
mv "${WORK_DIR}/dist" "${TARGET_DIST}"
rm -rf "${OLD_DIST}"

cat > "${BACKUP_DIR}/frontend_dist_install_report.json" <<EOF
{
  "success": true,
  "release_id": "${RELEASE_ID}",
  "target_dist": "${TARGET_DIST}",
  "backup_dir": "${BACKUP_DIR}",
  "preserve_old_assets": "${PRESERVE_OLD_ASSETS}",
  "preserved_asset_count": ${preserved_count}
}
EOF

printf 'SUCCESS\n'
printf 'target_dist: %s\n' "${TARGET_DIST}"
printf 'backup_dir: %s\n' "${BACKUP_DIR}"
printf 'preserved_asset_count: %s\n' "${preserved_count}"
