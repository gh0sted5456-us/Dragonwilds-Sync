#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
REPORT="${1:-release/package-test-report-linux.txt}"
mkdir -p "$(dirname "$REPORT")"
SERVICE="$ROOT/dist-service/DragonwildsSync.Service"
APPIMAGE="$(find "$ROOT/release" -maxdepth 1 -type f -name '*Ubuntu*.AppImage' -print -quit)"
HEADLESS="$(find "$ROOT/release" -maxdepth 1 -type f -name 'Dragonwilds-Sync-Headless-Ubuntu-*' -print -quit)"

pass() { printf 'PASS  %s\n' "$1" | tee -a "$REPORT"; }
fail() { printf 'FAIL  %s\n' "$1" | tee -a "$REPORT" >&2; exit 1; }
notrun() { printf 'NOT RUN  %s\n' "$1" | tee -a "$REPORT"; }

: > "$REPORT"
printf 'Dragonwilds Sync Ubuntu Release Candidate\n=========================================\n' | tee -a "$REPORT"
printf 'Generated: %s\n\n' "$(date -u +%FT%TZ)" | tee -a "$REPORT"

[[ -x "$SERVICE" ]] || fail 'Native packaged service exists and is executable'
pass 'Native packaged service exists and is executable'
probe='{"id":1,"method":"state.get","params":{}}'
output="$(printf '%s\n' "$probe" | "$SERVICE" 2>&1)" || fail 'Packaged service JSON-RPC stdio'
printf '%s' "$output" | grep -Eq '"id"[[:space:]]*:[[:space:]]*1' || fail 'Packaged service returned request id'
printf '%s' "$output" | grep -Eq '"ok"[[:space:]]*:[[:space:]]*true' || fail 'Packaged service returned ok=true'
pass 'Packaged service JSON-RPC stdio'
[[ -n "$HEADLESS" && -x "$HEADLESS" ]] || fail 'Standalone headless CLI exists and is executable'
HEADLESS_APPDATA="$(mktemp -d)"
headless_output="$(DRAGONWILDS_SYNC_APPDATA="$HEADLESS_APPDATA" "$HEADLESS" --headless profiles --json 2>&1)" || fail 'Standalone headless CLI profile probe'
rm -rf -- "$HEADLESS_APPDATA"
printf '%s' "$headless_output" | grep -Eq '^\[' || fail 'Standalone headless CLI returned profile JSON'
pass 'Standalone headless CLI profile probe'
crypto='{"id":2,"method":"application.cryptography.status","params":{}}'
crypto_output="$(printf '%s\n' "$crypto" | "$SERVICE" 2>&1)" || fail 'Packaged cryptography self-test RPC'
printf '%s' "$crypto_output" | grep -Eq '"id"[[:space:]]*:[[:space:]]*2' || fail 'Packaged cryptography self-test response'
pass 'Packaged cryptography self-test RPC'
[[ -d "$ROOT/renderer/assets/platforms" ]] || fail 'Platform icon source assets exist'
[[ -f "$ROOT/resources/recommended-mods.json" ]] || fail 'Recommended Mods default feed is packaged from resources'
[[ -f "$ROOT/renderer/vendor/monaco/vs/loader.js" ]] || fail 'Monaco runtime prepared'
pass 'Required launcher resources are present'
[[ -n "$APPIMAGE" && -f "$APPIMAGE" ]] || fail 'Ubuntu AppImage exists'
chmod +x "$APPIMAGE"
pass 'Ubuntu AppImage exists'
if command -v xvfb-run >/dev/null 2>&1; then
  set +e
  APPIMAGE_EXTRACT_AND_RUN=1 timeout 15s xvfb-run -a "$APPIMAGE" --no-sandbox >/tmp/dwsync-appimage.log 2>&1
  rc=$?
  set -e
  if [[ $rc -eq 124 ]]; then pass 'AppImage remained alive for 15-second headless boot smoke test';
  elif [[ $rc -eq 0 ]]; then fail 'AppImage exited during headless boot smoke test';
  else cat /tmp/dwsync-appimage.log >&2 || true; fail "AppImage headless boot smoke test (exit $rc)"; fi
else
  notrun 'AppImage headless boot smoke test (xvfb-run unavailable)'
fi
printf '\nREAL GAME / CROSS-PLATFORM ACCEPTANCE\n-------------------------------------\n' | tee -a "$REPORT"
notrun 'SteamCMD dedicated-server install on clean Ubuntu host'
notrun 'Real Dragonwilds dedicated-server launch'
notrun 'Windows client discovery of Ubuntu-hosted World'
notrun 'Windows client manifest/mod synchronization from Ubuntu host'
notrun 'RSDW live bridge on Linux/Proton'
printf '\nAutomated package result: READY FOR CLEAN-VM / GAME INTEGRATION TESTING\n' | tee -a "$REPORT"
sha256sum "$APPIMAGE" "$HEADLESS" "$SERVICE" > "$ROOT/release/checksums-linux.sha256"
