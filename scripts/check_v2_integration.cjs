'use strict';
const fs = require('fs');
const path = require('path');
const root = path.resolve(__dirname, '..');
const read = (p) => fs.readFileSync(path.join(root, p), 'utf8');
const must = (condition, message) => { if (!condition) throw new Error(message); };
const exists = (p) => fs.existsSync(path.join(root, p));

const index = read('renderer/index.html');
const css = read('renderer/release-v2-integration.css');
const js = read('renderer/release-v2-integration.js');
const remoteLifecycle = read('renderer/release-v2-remote-lifecycle.js');
const cardSizing = read('renderer/release-v2-card-sizing.js');
const trashUi = read('renderer/release-v2-trash.js');
const web = read('backend/directory_web.py');
const service = read('backend/dragonwilds_service.py');
const routing = read('backend/v2_remote_routing.py');
const cache = read('backend/rsdw_cache.py');
const spawner = read('backend/spawner_catalog.py');
const trash = read('backend/trash_store.py');
const registry = JSON.parse(read('docs/upstream-sources.json'));

must(index.includes('release-v2-integration.css') && index.includes('release-v2-integration.js'), 'Final V2 presentation layer is not loaded');
must(index.includes('release-v2-remote-lifecycle.js'), 'Remote Server listener lifecycle guard is not loaded');
must(index.includes('release-v2-card-sizing.js'), 'Tallest-placard sizing guard is not loaded');
must(index.includes('release-v2-trash.css') && index.includes('release-v2-trash.js'), 'Recoverable Trash UI is not loaded');
must(css.includes('grid-auto-rows:1fr') && css.includes('mask-image:linear-gradient'), 'Uniform placard/faded banner contract is missing');
must(cardSizing.includes("Math.max(...cards.map") && cardSizing.includes('card.style.minHeight'), 'Placards are not normalized to the tallest visible profile');
must(css.includes('data-dws-icon-mode="color"') && css.includes('data-dws-icon-mode="black"') && css.includes('data-dws-icon-mode="white"') && css.includes('data-dws-icon-mode="adaptive"'), 'Color/black/white/adaptive icon modes are incomplete');
must(js.includes('data-webhost-tab="remote"') && js.includes('remoteEnabled') && js.includes('webHostActivated'), 'Unified WebHost Remote Server/Declared visibility contract is missing');
must(js.includes('Users & Permissions') && js.includes('application.world_directory_host.user.create'), 'Remote Server user/permission manifest is not surfaced in WebHost');
must(remoteLifecycle.includes('payload.enabled=remoteEnabled') && remoteLifecycle.includes('payload.directory_enabled=false'), 'Remote-only listener does not release when Remote Server is disabled');
must(web.includes('WebHost only resolves the active heartbeat') && web.includes('remote_management') && web.includes('admin/login'), 'External WebHost Remote Server router is missing');
must(!web.includes('dws-router-password'), 'The routing hub must never collect a target server password');
must(service.includes('_legacy_handle = _legacy.handle'), 'V2 service wrapper must preserve the original handler before patching recursion');
must(service.includes('remote_server_choice_made') && service.includes('world.discovery.heartbeat'), 'External-heartbeat Remote Server default/explicit choice contract is missing');
must(routing.includes('target-world') && routing.includes('parsed.username') && routing.includes('parsed.password'), 'Remote endpoint sanitization/target authority is incomplete');
must(registry.sources['rsdw-icons'].path === 'website/shared/icons', 'RSDW icon path is not canonical');
must(registry.sources['rsdw-item-manifest'].path === 'data/items/json/RSDragonwilds', 'RSDW item JSON path is not canonical');
must(registry.sources['rsdw-item-manifest'].association_catalog === 'website/tools/item-editor/data/catalog.json', 'Exact RSDW item/icon association catalog is missing');
must(cache.includes('item-manifest.json') && cache.includes('iconPath') && cache.includes('"icon_ref": icon_ref') && cache.includes('"icon_path": icon_local'), 'Launcher-maintained exact RSDW item/icon manifest is missing');
must(spawner.includes('custom_items') && spawner.includes('"source": "dragonwilds-sync:mod-manifest"') && spawner.includes('Modded Items') && spawner.includes('"custom": True'), 'Spawner custom-item overlay / Modded Items category is missing');
must(trash.includes('copy one logical launcher object into Trash') || trash.includes('Copy one logical launcher object into Trash'), 'Verified Trash move contract is missing');
must(trashUi.includes('application.trash.restore') && trashUi.includes('application.trash.settings') && trashUi.includes('Empty Trash'), 'Trash restore/retention/empty controls are incomplete');
must(trashUi.includes('section.dataset.stamp') && trashUi.includes('mounting'), 'Trash observer rendering must be stamped/non-reentrant');

// The V2 shell relies on GitHub-managed content so docs/help/catalog changes do
// not require another executable release.
for (const file of ['docs/changelog.json','docs/changelog.html','docs/recommended-mods.json','docs/recommended-mods.html','help/manifest.json','renderer/assets/dragonwilds_icon.ico']) {
  must(exists(file), `Required V2 resource is missing: ${file}`);
}
must(exists('renderer/assets/platforms/steam.svg') && exists('renderer/assets/platforms/discord.svg') && exists('renderer/assets/platforms/nexusmods.svg') && exists('renderer/assets/platforms/windows.svg') && exists('renderer/assets/platforms/linux.svg'), 'Core platform/community icons are incomplete');

console.log('V2 integration contract: PASS');
