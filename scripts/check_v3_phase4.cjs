const fs = require('fs');
const path = require('path');
const root = path.resolve(__dirname, '..');
const failures = [];
const read = (rel) => fs.readFileSync(path.join(root, rel), 'utf8');
const need = (rel, values) => {
  const text = read(rel);
  for (const value of values) if (!text.includes(value)) failures.push(`${rel}: missing ${value}`);
  return text;
};
const needInsensitive = (rel, values) => {
  const text = read(rel);
  const folded = text.toLowerCase();
  for (const value of values) if (!folded.includes(String(value).toLowerCase())) failures.push(`${rel}: missing ${value}`);
  return text;
};

need('backend/v3_phase4.py', [
  'DragonwildsSync.V3Phase4Presentation.v1', 'normalize_tags', 'normalize_custom_badges', 'normalize_platforms',
  'destination_state', 'heartbeat_status', 'decorate_public_snapshot', 'asset_hash', 'Partial', 'Connecting',
  'max_png_dimension', 'tooltip_defaults_to_name', 'platform_refs', '_enrich_raw_from_profile'
]);
need('backend/v3_phase4_registry.py', [
  'DragonwildsSync.TagRegistry.v1', 'DragonwildsSync.PlatformRegistry.v1', 'Co-Op', 'aliases',
  'directSupportUrl', 'fallbackInfoUrl', 'nintendo-switch-2', 'verified'
]);
const badges = need('backend/v3_phase4_badges.py', [
  'BADGE_CACHE_DIR', 'MAX_BADGE_BYTES', 'MAX_BADGE_DIMENSION', '256', 'image/png', 'png_dimensions',
  'cache_badge_png', 'asset_hash', 'preview_data', 'add_badge', 'update_badge', 'remove_badge', 'reorder_badges', 'toggle_badge'
]);
if (!/BADGE_CACHE_DIR\s*=\s*APP_DATA_DIR\s*\/\s*["']cache["']\s*\/\s*["']custom-badges["']/.test(badges)) {
  failures.push('backend/v3_phase4_badges.py: custom badge cache must resolve under APP_DATA_DIR/cache/custom-badges');
}
need('backend/test_v3_phase4.py', [
  'canonical tags + aliases', 'central platform registry coverage', 'cached badge fetch + hash verification',
  'badge route traversal blocked', 'tooltip defaults to badge name', 'backend heartbeat truth', 'no embedded badge data'
]);
need('backend/dragonwilds_service.py', [
  'v3_phase4', 'v3.phase4.contract', 'v3.phase4.world_status', 'install_phase4_network',
  'v3.phase4.tags.registry', 'v3.phase4.platforms.registry', 'v3.phase4.badges.list', 'v3.phase4.badges.add',
  'v3.phase4.badges.update', 'v3.phase4.badges.toggle', 'v3.phase4.badges.remove', 'v3.phase4.badges.reorder'
]);
const renderer = need('renderer/release-v3-phase4.js', [
  'v3p4-placard', 'v3p4-back', 'data-v3p4-toggle', 'Page 1 / 2', 'Open Placard',
  'v3.phase4.world_status', "['full','reduced','off']", 'custom_badges',
  'heartbeatMarkup', 'Partial', 'data-v3p4-animation-settings', '__DWSYNC_V3_PHASE4__'
]);
const rendererFolded = renderer.toLowerCase();
for (const coreMod of ['dragonconnect']) {
  if (!rendererFolded.includes(coreMod)) failures.push(`renderer/release-v3-phase4.js: missing hidden-core-mod guard for ${coreMod}`);
}
need('renderer/release-v3-phase4.css', [
  'rotateY(180deg)', 'v3p4-back-scroll', 'data-v3p4-animations="reduced"', 'data-v3p4-animations="off"',
  '@keyframes v3p4-heart', 'v3p4-badge-rail', 'v3p4-window', 'v3p4-row-open'
]);
need('renderer/release-v3-phase4-manager.js', [
  'Custom Badge Manager', 'normalizePng', '256', 'image/png', 'v3.phase4.badges.list', 'v3.phase4.badges.add',
  'v3.phase4.badges.update', 'v3.phase4.badges.toggle', 'v3.phase4.badges.remove', 'v3.phase4.badges.reorder',
  'preview_data', 'openInAppBrowser', 'directSupportUrl', 'fallbackInfoUrl'
]);
need('renderer/release-v3-phase4-manager.css', ['v3p4-badge-manager', 'v3p4-badge-preview', 'v3p4-platform-link']);
need('backend/v3_phase4_web.py', ['dws-v3-phase4-web-script', 'dws-v3p4-back-scroll', 'Open Placard', 'prefers-reduced-motion', 'badge_refs', 'platform_refs']);
need('backend/v3_phase4_host_patch.py', ['_catalog_row', 'badge_refs', 'platform_refs', '_DWS_V3_PHASE4_BADGE_ROUTE_INSTALLED']);
need('backend/web_release_polish_hook.py', ['v3_phase4_web', 'v3_phase4_host_patch']);
need('renderer/release-v3-phase4-safety.js', ['v3p4-window', 'Open in Window', 'stopPropagation', '__DWSYNC_V3_PHASE4__']);
need('renderer/index.html', ['release-v3-phase4.css', 'release-v3-phase4-manager.css', 'release-v3-phase4.js', 'release-v3-phase4-safety.js', 'release-v3-phase4-manager.js']);
const phase4State = needInsensitive('PROJECT_STATE/V3_PHASE4.md', ['Front/Back', 'Animations Full/Reduced/Off', 'Custom badges', 'Heartbeat', 'WebHost']);
const phase4StateFolded = phase4State.toLowerCase();
if (!(phase4StateFolded.includes('horizontal') && phase4StateFolded.includes('open') && (phase4StateFolded.includes('right-click') || phase4StateFolded.includes('right click')))) {
  failures.push('PROJECT_STATE/V3_PHASE4.md: missing horizontal right-click Open contract');
}

if (/setInterval\([^,]+,\s*(?:[1-9]\d{0,3})\s*\)/.test(renderer)) failures.push('Phase 4 renderer must not introduce high-frequency polling');
const manager = read('renderer/release-v3-phase4-manager.js');
if (/data:image\/(?:jpeg|webp|gif)/i.test(manager)) failures.push('Custom badge manager must accept PNG data only');
if (!manager.includes('routine heartbeats publish only the badge ID/hash reference')) failures.push('Badge manager must explain reference-only heartbeat behavior');

const backend = read('backend/v3_phase4.py');
if (backend.includes('start_background(') || backend.includes('threading.Thread')) failures.push('Phase 4 helper must not create a second heartbeat scheduler');
if (!backend.includes('MAX_CUSTOM_BADGE_BYTES')) failures.push('Custom badge PNG size must be bounded');
if (!badges.includes('temp.replace(target)')) failures.push('Badge cache writes must be atomic');
if (badges.includes('preview_data') && read('backend/v3_phase4.py').includes('preview_data')) failures.push('Preview PNG data must never enter the heartbeat/publication helper');

if (failures.length) {
  console.error('[V3 Phase 4] FAIL');
  failures.forEach((failure) => console.error(` - ${failure}`));
  process.exit(1);
}
console.log('[V3 Phase 4] PASS · placards, aliases/registries, badge manager/cache, platform navigation, WebHost and backend heartbeat contract verified');
