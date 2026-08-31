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
# Materialize Electron before its CI preload smoke test. The smoke BrowserWindow
# retains renderer sandboxing and context isolation; its script bypasses only
# the hosted runner's outer SUID sandbox, which can stall before app readiness.
if [[ "${CI:-}" == "true" ]]; then
  node node_modules/electron/install.js
  test -f node_modules/electron/dist/chrome-sandbox
  sudo -n chown root:root node_modules/electron/dist/chrome-sandbox
  sudo -n chmod 4755 node_modules/electron/dist/chrome-sandbox
fi
npm run verify
if command -v xvfb-run >/dev/null 2>&1; then
  # Hosted runners can inherit a synthetic DBUS_SESSION_BUS_ADDRESS that
  # Chromium cannot parse. Give the sandboxed preload test a real private
  # session bus when available; otherwise remove the invalid inherited value.
  if command -v dbus-run-session >/dev/null 2>&1; then
    dbus-run-session -- xvfb-run -a npm run test:preload
  else
    env -u DBUS_SESSION_BUS_ADDRESS xvfb-run -a npm run test:preload
  fi
else
  echo "[WARN] xvfb-run is unavailable; sandbox preload bridge smoke test was not run."
fi
# GitHub Actions sets CI, which otherwise makes electron-builder attempt an
# actual GitHub release. RC packaging is artifact-only and requires no token.
npx electron-builder --linux AppImage --publish never
VERSION="$(node -p "require('./package.json').version")"
HEADLESS_NAME="Dragonwilds Sync Headless"
HEADLESS_RELEASE="release/${HEADLESS_NAME}"
HEADLESS_ARCHIVE="release/${HEADLESS_NAME}.tar.gz"
cp dist-service/DragonwildsSync.Service "$HEADLESS_RELEASE"
chmod 755 "$HEADLESS_RELEASE"
tar -C release -czf "$HEADLESS_ARCHIVE" "$HEADLESS_NAME"
rm -f "$HEADLESS_RELEASE"
bash scripts/test_packaged_linux.sh
echo "Ubuntu release-candidate build complete. See release/ for the AppImage, headless CLI tarball, checksums, and package-test report."
