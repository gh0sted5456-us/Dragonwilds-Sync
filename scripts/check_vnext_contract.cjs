'use strict';
const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const read = (p) => fs.readFileSync(path.join(root, p), 'utf8');
const must = (condition, message) => { if (!condition) throw new Error(message); };

const index = read('renderer/index.html');
const vnext = read('renderer/release-vnext.js');
const css = read('renderer/release-vnext.css');
const helpMedia = read('renderer/release-vnext-help-media.js');
const helpMediaCss = read('renderer/release-vnext-help-media.css');
const web = read('backend/directory_web.py');
const legacy = read('backend/directory_web_legacy.py');
const manifest = JSON.parse(read('help/manifest.json'));

must(index.includes('release-vnext.css') && index.includes('release-vnext.js'), 'vNext renderer assets are not loaded');
must(index.includes('release-vnext-help-media.css') && index.includes('release-vnext-help-media.js'), 'Live Help walkthrough media assets are not loaded');
must(vnext.includes('data-vnext-world-tab') && vnext.includes('Declared Worlds'), 'Desktop Declared World source is missing');
must(vnext.includes('/api/v1/worlds?active=sync') && vnext.includes('directory_verified') && vnext.includes('fingerprint_claimed') && vnext.includes('last_seen'), 'Declared semantics must come from the verified live Sync heartbeat feed');
must(vnext.includes('dws-profile-badges') && css.includes('.world-list-row .world-list-title .dws-profile-badges'), 'Profile badges are not shared with horizontal rows');
must(vnext.includes('Refresh Help') && vnext.includes('dragonwilds-sync-help-v1'), 'Refreshable cached Help shell is missing');
must(helpMedia.includes('raw.githubusercontent.com') && helpMedia.includes('dws-help-figure') && helpMedia.includes('loading = \'lazy\''), 'Live Help image rendering must remain GitHub-scoped and lazy-loaded');
must(helpMediaCss.includes('.dws-help-figure') && helpMediaCss.includes('object-fit:contain'), 'Live Help image layout contract is missing');
must(manifest.schema === 'DragonwildsSync.Help.v1' && Array.isArray(manifest.pages) && manifest.pages.length >= 5, 'Help manifest schema/pages invalid');
for (const page of manifest.pages) {
  must(page.id && page.title && page.markdown, `Help page entry is incomplete: ${JSON.stringify(page)}`);
  must(fs.existsSync(path.join(root, 'help', page.markdown)), `Help page is missing: ${page.markdown}`);
}
must(web.includes('directory_web_legacy') && web.includes('_legacy_public_browser_html'), 'Public WebGUI wrapper must preserve the prior implementation');
must(web.includes('data-filter=\\"declared\\"') || web.includes('data-filter="declared"'), 'Public Declared filter is missing');
must(web.includes('/api/v1/worlds?active=sync') && web.includes('directory_verified') && web.includes('fingerprint_claimed'), 'Public Declared projection must use verified Sync heartbeat rows');
must(web.includes('horizontalCard') && web.includes('profileBadges'), 'Public horizontal/profile badge parity is missing');
must(legacy.includes('def public_browser_html') && legacy.includes('def remote_admin_html'), 'Preserved public/admin WebGUI implementation is incomplete');

console.log('vNext contract: PASS');
