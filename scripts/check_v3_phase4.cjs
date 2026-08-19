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

need('backend/v3_phase4.py', [
  'DragonwildsSync.V3Phase4Presentation.v1', 'normalize_tags', 'normalize_custom_badges', 'normalize_platforms',
  'destination_state', 'heartbeat_status', 'decorate_public_snapshot', 'image_data', 'asset_hash', 'Partial', 'Connecting'
]);
need('backend/test_v3_phase4.py', ['canonical tags', 'trusted platforms', 'badge references', 'backend heartbeat truth', 'no embedded badge data']);
need('backend/dragonwilds_service.py', ['v3_phase4', 'v3.phase4.contract', 'v3.phase4.world_status', 'install_phase4_network']);
need('renderer/release-v3-phase4.js', [
  'v3p4-placard', 'v3p4-back', 'data-v3p4-toggle', 'Page 1 / 2', 'Open Placard',
  'v3.phase4.world_status', "['full','reduced','off']", 'custom_badges', 'DragonCore', 'DragonConnect',
  'heartbeatMarkup', 'Partial', 'data-v3p4-animation-settings', '__DWSYNC_V3_PHASE4__'
]);
need('renderer/release-v3-phase4.css', [
  'rotateY(180deg)', 'v3p4-back-scroll', 'data-v3p4-animations="reduced"', 'data-v3p4-animations="off"',
  '@keyframes v3p4-heart', 'v3p4-badge-rail', 'v3p4-window', 'v3p4-row-open'
]);
need('backend/v3_phase4_web.py', ['dws-v3-phase4-web-script', 'dws-v3p4-back-scroll', 'Open Placard', 'prefers-reduced-motion', 'badge_refs']);
need('backend/web_release_polish_hook.py', ['v3_phase4_web']);
need('renderer/release-v3-phase4-safety.js', ['v3p4-window', 'Open in Window', 'stopPropagation', '__DWSYNC_V3_PHASE4__']);
need('renderer/index.html', ['release-v3-phase4.css', 'release-v3-phase4.js', 'release-v3-phase4-safety.js']);
need('PROJECT_STATE/V3_PHASE4.md', ['Placard Front/Back', 'Animations Full/Reduced/Off', 'Horizontal right-click Open', 'Custom badges', 'Heartbeat', 'WebHost']);

const renderer = read('renderer/release-v3-phase4.js');
if (/setInterval\([^,]+,\s*(?:[1-9]\d{0,3})\s*\)/.test(renderer)) failures.push('Phase 4 renderer must not introduce high-frequency polling');
if (/data:image\/(?:jpeg|webp|gif)/i.test(renderer)) failures.push('Custom badge renderer must accept PNG data only');

const backend = read('backend/v3_phase4.py');
if (backend.includes('start_background(') || backend.includes('threading.Thread')) failures.push('Phase 4 helper must not create a second heartbeat scheduler');
if (!backend.includes('MAX_CUSTOM_BADGE_BYTES')) failures.push('Custom badge PNG size must be bounded');

if (failures.length) {
  console.error('[V3 Phase 4] FAIL');
  failures.forEach((failure) => console.error(` - ${failure}`));
  process.exit(1);
}
console.log('[V3 Phase 4] PASS · two-sided placards, animation modes, tags/badges/platforms, WebHost Open and backend-owned heartbeat contract verified');
