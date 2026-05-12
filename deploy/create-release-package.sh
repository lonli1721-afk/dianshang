#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${1:-/tmp}"
TIMESTAMP="$(date +%Y%m%d-%H%M)"
OUT_PATH="${OUT_DIR%/}/game-video-tool-${TIMESTAMP}.tar.gz"
NPM_BIN="${NPM_BIN:-}"
TMP_DIR=""

cleanup() {
  if [[ -n "${TMP_DIR}" && -d "${TMP_DIR}" ]]; then
    rm -rf "${TMP_DIR}"
  fi
}
trap cleanup EXIT

if [[ -z "${NPM_BIN}" ]]; then
  for candidate in "${HOME}"/.nvm/versions/node/*/bin/npm; do
    [[ -e "${candidate}" ]] && NPM_BIN="${candidate}"
  done
fi

if [[ -z "${NPM_BIN}" ]] && command -v npm >/dev/null 2>&1; then
  NPM_BIN="$(command -v npm)"
fi

if [[ -z "${NPM_BIN}" ]]; then
  echo "npm not found. Set NPM_BIN=/path/to/npm and retry." >&2
  exit 1
fi

cd "${ROOT_DIR}/react-ui"
export PATH="$(dirname "${NPM_BIN}"):${PATH}"
"${NPM_BIN}" run build

mkdir -p "${OUT_DIR}"
TMP_DIR="$(mktemp -d)"
ln -s "${ROOT_DIR}" "${TMP_DIR}/game-video-tool"

export COPYFILE_DISABLE=1
tar --no-xattrs -czhf "${OUT_PATH}" \
  --exclude="game-video-tool/.git" \
  --exclude="game-video-tool/.claude" \
  --exclude="game-video-tool/.codex" \
  --exclude="game-video-tool/.env" \
  --exclude="game-video-tool/.local-data" \
  --exclude="game-video-tool/.tmp-*" \
  --exclude="game-video-tool/.tmp-data" \
  --exclude="game-video-tool/.venv" \
  --exclude="game-video-tool/.viral-*" \
  --exclude="game-video-tool/react-ui/src/pages/ImageToolboxPage.jsx" \
  --exclude="game-video-tool/react-ui/node_modules" \
  --exclude="game-video-tool/server/uploads" \
  --exclude="game-video-tool/server/cache" \
  --exclude="game-video-tool/server/routers/image_tools_routes.py" \
  --exclude="game-video-tool/**/__pycache__" \
  --exclude="game-video-tool/**/*.pyc" \
  --exclude="game-video-tool/*.db" \
  --exclude="game-video-tool/*.log" \
  --exclude="game-video-tool/*.tar.gz" \
  -C "${TMP_DIR}" \
  game-video-tool

echo "${OUT_PATH}"
