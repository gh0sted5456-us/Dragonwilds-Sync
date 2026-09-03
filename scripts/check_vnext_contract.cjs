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
const helpyPage = read('website/helpy.html');
const helpyScript = read('website/helpy.js');
const packageConfig = JSON.parse(read('package.json'));
const web = read('backend/directory_web.py');
const compat = read('backend/directory_web_compat.py');
const manifest = JSON.parse(read('help/manifest.json'));

must(index.includes('release-vnext.css') && index.includes('release-vnext.js'), 'vNext renderer assets are not loaded');
must(index.includes('release-vnext-help-media.css') && index.includes('release-vnext-help-media.js'), 'Live Help walkthrough media assets are not loaded');
must(vnext.includes('data-vnext-world-tab') && vnext.includes('Declared Worlds'), 'Desktop Declared World source is missing');
must(vnext.includes('/api/v1/worlds?active=sync') && vnext.includes('directory_verified') && vnext.includes('fingerprint_claimed') && vnext.includes('last_seen'), 'Declared semantics must come from the verified live Sync heartbeat feed');
must(vnext.includes('dws-profile-badges') && css.includes('.world-list-row .world-list-title .dws-profile-badges'), 'Profile badges are not shared with horizontal rows');
must(vnext.includes("new Set(['UE4SS','RUNESCHEMA'])") && vnext.includes("label === 'VANILLA' && modded") && vnext.includes("redundant.add('SINGLEPLAYER')"), 'Profile badge cleanup must hide redundant runtime labels, stale Vanilla, and server-only local labels');
must(vnext.includes('Refresh Help') && vnext.includes('dragonwilds-sync-help-v1'), 'Refreshable cached Help shell is missing');
must(helpMedia.includes('raw.githubusercontent.com') && helpMedia.includes('dws-help-figure') && helpMedia.includes('loading = \'lazy\''), 'Live Help image rendering must remain GitHub-scoped and lazy-loaded');
must(helpMediaCss.includes('.dws-help-figure') && helpMediaCss.includes('object-fit:contain'), 'Live Help image layout contract is missing');
must(helpyPage.includes('helpy.js') && helpyPage.includes('help/manifest.json'), 'Website Helpy route must identify the shared JSON source');
must(helpyScript.includes('manifest.json') && helpyScript.includes('page.sections'), 'Website Helpy must render structured manifest content');
must(packageConfig.build.files.includes('!renderer/assets/help/**/*'), 'Application packages must leave website-owned Helpy screenshots out of the desktop bundle');
must(vnext.includes('helpy-website-shell') && index.includes('gh0sted5456-us.github.io'), 'Desktop Helpy must prefer the published website route');
must(manifest.schema === 'DragonwildsSync.Help.v1' && Array.isArray(manifest.pages) && manifest.pages.length >= 5, 'Help manifest schema/pages invalid');
for (const page of manifest.pages) {
  must(page.id && page.title && page.summary && Array.isArray(page.sections) && page.sections.length, `Help page entry is incomplete: ${JSON.stringify(page)}`);
  must(page.sections.every((section) => section.title && (section.body || (Array.isArray(section.steps) && section.steps.length))), `Help page section is incomplete: ${page.id}`);
}
must(web.includes('directory_web_legacy') && web.includes('_legacy_public_browser_html'), 'Public WebGUI wrapper must preserve the prior implementation');
must(web.includes('data-filter=\\"declared\\"') || web.includes('data-filter="declared"'), 'Public Declared filter is missing');
must(web.includes('/api/v1/worlds?active=sync') && web.includes('directory_verified') && web.includes('fingerprint_claimed'), 'Public Declared projection must use verified Sync heartbeat rows');
must(web.includes('horizontalCard') && web.includes('profileBadges'), 'Public horizontal/profile badge parity is missing');
must(web.includes('worldIsModded') && web.includes("new Set(['UE4SS','RUNESCHEMA'])") && web.includes("v==='VANILLA'&&worldIsModded(w)"), 'Public cards must share the Vanilla/runtime/server badge cleanup');
must(compat.includes('def public_browser_html') && compat.includes('def remote_admin_html'), 'Preserved public/admin WebGUI compatibility implementation is incomplete');

console.log('vNext contract: PASS');
