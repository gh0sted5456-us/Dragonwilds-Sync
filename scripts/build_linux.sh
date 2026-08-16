#!/usr/bin/env bash
set -Eeuo pipefail

project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "[ERROR] Linux packages must be built on Linux. Use the included GitHub Actions workflow from Windows." >&2
  exit 2
fi
if [[ ! -f package.json || ! -f backend/DragonwildsSync.Service.spec ]]; then
  echo "[ERROR] Run this script from the complete Dragonwilds Sync source tree." >&2
  exit 2
fi

system_python="${PYTHON:-python3}"
npm_bin="${NPM:-npm}"
build_flatpak="${BUILD_FLATPAK:-1}"
venv_dir="${DWSYNC_LINUX_VENV:-$project_root/.venv-linux-build}"
log_path="$project_root/build-linux.log"
exec > >(tee "$log_path") 2>&1

require_command() {
  command -v "$1" >/dev/null 2>&1 || { echo "[ERROR] Required command not found: $1"; exit 3; }
}

echo "============================================================"
echo " Dragonwilds Sync V1 — Linux / Flatpak Build"
echo "============================================================"
echo "Project: $project_root"
echo "Started: $(date --iso-8601=seconds)"

require_command "$system_python"
require_command "$npm_bin"
require_command grep
require_command tar

echo "[1/8] Toolchain"
"$system_python" --version
"$npm_bin" --version
node --version

echo "[2/8] Dependencies"
"$system_python" -m venv "$venv_dir"
python_bin="$venv_dir/bin/python"
"$python_bin" -m pip install --upgrade pip
"$python_bin" -m pip install --upgrade -r backend/requirements-build.txt
"$npm_bin" ci --include=dev

echo "[3/8] Verification"
"$npm_bin" run verify

echo "[4/8] Cleaning Linux-owned outputs"
rm -rf -- "$project_root/dist-service-linux" "$project_root/build-service-linux" "$project_root/release-linux" "$project_root/flatpak-build" "$project_root/flatpak-repo"
mkdir -p "$project_root/release-linux"

echo "[5/8] Native Linux JSON-RPC service"
"$python_bin" -m PyInstaller --clean --noconfirm \
  --distpath "$project_root/dist-service-linux" \
  --workpath "$project_root/build-service-linux" \
  "$project_root/backend/DragonwildsSync.Service.spec"
service_bin="$project_root/dist-service-linux/DragonwildsSync.Service"
[[ -x "$service_bin" ]] || { echo "[ERROR] PyInstaller did not produce $service_bin"; exit 4; }
probe_output="$(printf '%s\n' '{"id":1,"method":"state.get","params":{}}' | "$service_bin")"
grep -Eq '"id"[[:space:]]*:[[:space:]]*1' <<<"$probe_output"
grep -Eq '"ok"[[:space:]]*:[[:space:]]*true' <<<"$probe_output"
crypto_probe="$(printf '%s\n' '{"id":2,"method":"application.cryptography.status","params":{}}' | "$service_bin")"
grep -Eq '"healthy"[[:space:]]*:[[:space:]]*true' <<<"$crypto_probe"
grep -Eq '"sign_verify"[[:space:]]*:[[:space:]]*true' <<<"$crypto_probe"
grep -Eq '"serialization_reload"[[:space:]]*:[[:space:]]*true' <<<"$crypto_probe"
grep -Eq '"invalid_signature_rejected"[[:space:]]*:[[:space:]]*true' <<<"$crypto_probe"
echo "[OK] Packaged Ed25519 runtime passed generation/sign/serialization/rejection tests."

echo "[6/8] AppImage and portable tar.gz"
./node_modules/.bin/electron-builder --linux --config.directories.output=release-linux
[[ -d release-linux/linux-unpacked ]] || { echo "[ERROR] electron-builder did not produce linux-unpacked."; exit 5; }
find release-linux -maxdepth 1 -type f -printf '  %f\n' | sort

if [[ "$build_flatpak" == "0" ]]; then
  echo "[7/8] Flatpak skipped because BUILD_FLATPAK=0"
else
  echo "[7/8] Flatpak bundle"
  require_command flatpak
  require_command flatpak-builder
  flatpak --user remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
  flatpak --user install -y flathub \
    org.freedesktop.Platform//24.08 \
    org.freedesktop.Sdk//24.08 \
    org.electronjs.Electron2.BaseApp//24.08
  flatpak-builder --force-clean --user --install-deps-from=flathub \
    --repo="$project_root/flatpak-repo" \
    "$project_root/flatpak-build" \
    "$project_root/packaging/flatpak/com.dragonwilds.sync.yml"
  flatpak build-bundle "$project_root/flatpak-repo" \
    "$project_root/release-linux/Dragonwilds-Sync-1.0.0-x86_64.flatpak" \
    com.dragonwilds.sync stable
fi

echo "[8/8] Reproducible raw-source folder"
node scripts/package_raw_source.cjs
raw_source_dir="$project_root/Codex Outputs/DragonwildsSync_V1_Raw_Source"
[[ -f "$raw_source_dir/RAW_SOURCE_CONTENTS.md" ]] || { echo "[ERROR] Raw source staging failed."; exit 6; }

echo "BUILD COMPLETE: $project_root/release-linux"
echo "Finished: $(date --iso-8601=seconds)"
