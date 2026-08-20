#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
[[ "$(uname -s)" == "Linux" ]] || { echo "[ERROR] Linux build must run on Linux." >&2; exit 1; }
if [[ -r /etc/os-release ]]; then
  . /etc/os-release
  [[ "${ID:-}" == "ubuntu" ]] || echo "[WARN] Ubuntu is the supported baseline; detected ${PRETTY_NAME:-Linux}."
fi
PYTHON_BIN="${DRAGONWILDS_SYNC_PYTHON:-python3}"
VENV="$ROOT/.venv-build"
"$PYTHON_BIN" -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/python" -m pip install -r backend/requirements-build.txt
rm -rf build-service dist-service release
"$VENV/bin/pyinstaller" --noconfirm --clean --distpath dist-service --workpath build-service backend/DragonwildsSync.Service.spec
test -x dist-service/DragonwildsSync.Service
npm ci --include=dev
npm run verify
if command -v xvfb-run >/dev/null 2>&1; then
  xvfb-run -a npm run test:preload
else
  echo "[WARN] xvfb-run is unavailable; sandbox preload bridge smoke test was not run."
fi
# GitHub Actions sets CI, which otherwise makes electron-builder attempt an
# actual GitHub release. RC packaging is artifact-only and requires no token.
npx electron-builder --linux AppImage --publish never
bash scripts/test_packaged_linux.sh
echo "Ubuntu release-candidate build complete. See release/ for the AppImage, checksums, and package-test report."
