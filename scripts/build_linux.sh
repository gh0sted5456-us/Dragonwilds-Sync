#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
[[ "$(uname -s)" == "Linux" ]] || { echo "[ERROR] Linux build must run on Linux." >&2; exit 1; }
if [[ -r /etc/os-release ]]; then . /etc/os-release; [[ "${ID:-}" == "ubuntu" ]] || echo "[WARN] Ubuntu is the supported baseline; detected ${PRETTY_NAME:-Linux}."; fi
PYTHON_BIN="${DRAGONWILDS_SYNC_PYTHON:-python3}"
VENV="$ROOT/.venv-build"
"$PYTHON_BIN" -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/python" -m pip install -r backend/requirements-build.txt
rm -rf build-service dist-service
"$VENV/bin/pyinstaller" --noconfirm --clean --distpath dist-service --workpath build-service backend/DragonwildsSync.Service.spec
test -x dist-service/DragonwildsSync.Service
npm ci --include=dev
npm run verify
npx electron-builder --linux AppImage
echo "Ubuntu build complete. See release/ for the AppImage."
