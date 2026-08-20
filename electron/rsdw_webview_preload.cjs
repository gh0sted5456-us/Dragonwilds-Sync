const { ipcRenderer } = require('electron');
let hydrating = false;
let dirtyTimer = null;
let previewTimer = null;
let capturePurpose = 'save';
let latestPalette = {};
const appearanceMode = new URLSearchParams(location.search).get('dws-mode') === 'appearance';

function post(channel, payload = {}) {
  try { ipcRenderer.sendToHost(channel, payload); } catch (_) {}
}

function waitForCharacterInput(timeoutMs = 12000) {
  return new Promise((resolve, reject) => {
    const started = Date.now();
    const tick = () => {
      const input = document.querySelector('#character-file');
      if (input) return resolve(input);
      if (Date.now() - started > timeoutMs) return reject(new Error('RSDWTools character input was not found.'));
      setTimeout(tick, 100);
    };
    tick();
  });
}

async function hydrateCharacter(payload) {
  try {
    hydrating = true;
    const text = String(payload?.text || '');
    const fileName = String(payload?.fileName || 'Character.json');
    if (!text) throw new Error('No character data was supplied.');
    const input = await waitForCharacterInput();
    const file = new File([text], fileName, { type: 'application/json', lastModified: Date.now() });
    const transfer = new DataTransfer();
    transfer.items.add(file);
    input.files = transfer.files;
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
    document.body?.classList.add('dws-embedded', 'dws-hydrated');
    latestPalette = payload?.avatar?.palette || {};
    preserveCurrentAppearanceOptions(text);
    decorateAppearanceControls(latestPalette);
    post('rsdw-hydrated', { token: payload?.token || 0, fileName });
  } catch (error) {
    post('rsdw-hydration-error', { token: payload?.token || 0, message: error?.message || String(error) });
  } finally {
    setTimeout(() => { preserveCurrentAppearanceOptions(String(payload?.text || '')); decorateAppearanceControls(latestPalette); hydrating = false; reportContentSize(); }, 900);
  }
}

function paletteForField(key) {
  if (key === 'SkinTone') return latestPalette.skin || [];
  if (key === 'HairColor' || key === 'EyebrowColor') return latestPalette.hair || [];
  if (key === 'EyeColor') return latestPalette.eyes || [];
  return [];
}

function paletteIndex(key, value) {
  const match = String(value || '').match(/(\d{1,3})$/);
  if (!match) return -1;
  const number = Number(match[1]);
  return key === 'SkinTone' ? Math.max(0, number * 2 - 2) : Math.max(0, number - 1);
}

function decorateAppearanceControls(palette = latestPalette) {
  latestPalette = palette || {};
  document.querySelectorAll('[data-customization]').forEach((select) => {
    const key = select.dataset.customization || '';
    const rows = paletteForField(key);
    if (!rows.length) return;
    const field = select.closest('.character-field');
    if (!field) return;
    let grid = field.querySelector('.dws-color-swatches');
    if (!grid) {
      grid = document.createElement('div');
      grid.className = 'dws-color-swatches';
      grid.setAttribute('role', 'listbox');
      grid.setAttribute('aria-label', `${key} colors`);
      field.appendChild(grid);
    }
    grid.replaceChildren();
    [...select.options].forEach((option) => {
      const row = rows[paletteIndex(key, option.value)];
      if (!row?.hex) return;
      const swatch = document.createElement('button');
      swatch.type = 'button';
      swatch.className = `dws-color-swatch${select.value === option.value ? ' selected' : ''}`;
      swatch.style.setProperty('--swatch', row.hex);
      swatch.title = `${option.textContent || option.value} · ${row.label || row.id}`;
      swatch.setAttribute('aria-label', swatch.title);
      swatch.setAttribute('aria-selected', select.value === option.value ? 'true' : 'false');
      swatch.addEventListener('click', () => {
        select.value = option.value;
        select.dispatchEvent(new Event('input', { bubbles: true }));
        select.dispatchEvent(new Event('change', { bubbles: true }));
        decorateAppearanceControls(latestPalette);
      });
      grid.appendChild(swatch);
    });
  });
}

function reportContentSize() {
  const root = document.querySelector('.item-editor-wrapper, .page-layout, main');
  const rect = root?.getBoundingClientRect?.();
  const height = Math.ceil(Math.max(root?.offsetHeight || 0, rect ? rect.bottom + window.scrollY : 0));
  if (height) post('rsdw-content-size', { height });
}

function findCustomizationData(value) {
  if (!value || typeof value !== 'object') return null;
  if (value.CustomizationData && typeof value.CustomizationData === 'object') return value.CustomizationData;
  for (const child of Object.values(value)) {
    const found = findCustomizationData(child);
    if (found) return found;
  }
  return null;
}

function preserveCurrentAppearanceOptions(text) {
  try {
    const current = findCustomizationData(JSON.parse(String(text || '{}'))) || {};
    document.querySelectorAll('[data-customization]').forEach((select) => {
      const entry = current[select.dataset.customization];
      const value = String(entry?.rowName ?? entry?.RowName ?? entry ?? '').trim();
      if (!value) return;
      if (![...select.options].some((option) => option.value === value)) {
        const option = new Option(`${value} · current save`, value);
        option.dataset.dwsCurrent = '1';
        select.add(option);
      }
      select.value = value;
    });
  } catch (_) {}
}

function applyAppearanceMode() {
  if (!appearanceMode) return;
  document.body?.classList.add('dws-appearance-mode');
  const panel = document.querySelector('.character-editor-panel');
  const grid = document.querySelector('#customization-grid');
  if (panel && grid) {
    const title = grid.previousElementSibling;
    [...panel.children].forEach((child) => {
      if (child !== grid && child !== title && child.id !== 'character-file') child.style.display = 'none';
    });
    if (title) title.textContent = 'Rebuild Character Appearance';
  }
  if (!document.querySelector('#dws-appearance-style')) {
    const style = document.createElement('style');
    style.id = 'dws-appearance-style';
    style.textContent = `
      #rsdw-header-mount,.landing-logo__dropdown,#rsdw-footer-mount{display:none!important}
      body.dws-appearance-mode{min-height:100vh!important;background:#0b0d0f!important;padding:18px!important}
      body.dws-appearance-mode .item-editor-wrapper,body.dws-appearance-mode .page-layout{display:block!important;min-height:0!important;width:100%!important;margin:0!important;padding:0!important}
      body.dws-appearance-mode .character-editor-panel{display:block!important;min-height:0!important;width:100%!important;max-width:none!important;margin:0!important;padding:18px!important}
      body.dws-appearance-mode #customization-grid{display:grid!important;grid-template-columns:repeat(auto-fit,minmax(210px,1fr))!important;gap:14px!important}
      body.dws-appearance-mode #customization-grid .character-field{min-width:0!important}
    `;
    document.head.appendChild(style);
  }
}

function requestSave(purpose = 'save') {
  const button = document.querySelector('#save-button');
  if (!button || button.disabled || button.classList.contains('hidden')) {
    post('rsdw-save-error', { message: 'The RSDW editor has not exposed a save action yet.' });
    return;
  }
  capturePurpose = purpose === 'preview' ? 'preview' : 'save';
  button.click();
}

function requestPreview() {
  if (hydrating) return;
  clearTimeout(previewTimer);
  previewTimer = setTimeout(() => requestSave('preview'), 180);
}

// Upstream editors normally download their edited JSON. In the embedded Toolkit,
// capture that exact JSON and hand it back to Dragonwilds Sync for backup-first,
// optimistic-concurrency writeback instead of silently dropping a file in Downloads.
const originalAnchorClick = HTMLAnchorElement.prototype.click;
const originalCreateObjectURL = URL.createObjectURL.bind(URL);
const originalRevokeObjectURL = URL.revokeObjectURL.bind(URL);
const generatedBlobs = new Map();
URL.createObjectURL = function patchedCreateObjectURL(blob) {
  const url = originalCreateObjectURL(blob);
  if (blob instanceof Blob) generatedBlobs.set(url, blob);
  return url;
};
URL.revokeObjectURL = function patchedRevokeObjectURL(url) {
  if (generatedBlobs.has(String(url))) {
    setTimeout(() => { generatedBlobs.delete(String(url)); originalRevokeObjectURL(url); }, 1500);
    return;
  }
  originalRevokeObjectURL(url);
};
HTMLAnchorElement.prototype.click = function patchedAnchorClick() {
  try {
    const download = String(this.download || '');
    const href = String(this.href || '');
    if (download.toLowerCase().endsWith('.json') && href.startsWith('blob:')) {
      const blob = generatedBlobs.get(href);
      (blob ? blob.text() : fetch(href).then((response) => response.text()))
        .then((text) => {
          const channel = capturePurpose === 'preview' ? 'rsdw-preview' : 'rsdw-save';
          capturePurpose = 'save';
          post(channel, { text, fileName: download });
        })
        .catch((error) => post('rsdw-save-error', { message: error?.message || String(error) }));
      return;
    }
  } catch (_) {}
  return originalAnchorClick.call(this);
};

ipcRenderer.on('hydrate-rsdw-character', (_event, payload) => hydrateCharacter(payload || {}));
ipcRenderer.on('request-rsdw-save', () => requestSave('save'));

window.addEventListener('DOMContentLoaded', () => {
  document.body?.classList.add('dws-embedded');
  if (/\/Avatar\/index\.html$/i.test(location.pathname)) {
    const style = document.createElement('style');
    style.id = 'dws-avatar-viewport-only';
    style.textContent = `
      html,body{width:100%!important;height:100%!important;min-height:100%!important;margin:0!important;overflow:hidden!important;background:#090b0c!important}
      body>*:not(main):not(#avatar-stage){display:none!important}
      main{display:block!important;position:fixed!important;inset:0!important;width:100vw!important;height:100vh!important;margin:0!important;padding:0!important;background:#090b0c!important}
      main>*:not(.avatar-layout):not(#avatar-stage){display:none!important}
      .avatar-layout{display:block!important;position:fixed!important;inset:0!important;width:100vw!important;height:100vh!important;margin:0!important;padding:0!important}
      .avatar-layout>*:not(.avatar-viewer-panel):not(#avatar-stage),.avatar-controls,#rsdw-header-mount,#rsdw-footer-mount,.avatar-shell__controls,.avatar-sidebar{display:none!important}
      .avatar-viewer-panel{display:block!important;position:fixed!important;inset:0!important;width:100vw!important;height:100vh!important;margin:0!important;padding:0!important;border:0!important;background:#090b0c!important}
      .avatar-viewer-panel>*:not(#avatar-stage){display:none!important}
      #avatar-stage{display:block!important;position:fixed!important;inset:0!important;width:100vw!important;height:100vh!important;min-height:100vh!important;margin:0!important;background:#090b0c!important}
      #avatar-stage canvas{display:block!important;width:100vw!important;height:100vh!important}
    `;
    document.head.appendChild(style);
  }
  applyAppearanceMode();
  if (!document.querySelector('#dws-native-style')) {
    const style = document.createElement('style');
    style.id = 'dws-native-style';
    style.textContent = `
      html,body.dws-embedded{height:auto!important;min-height:100%!important;overflow-x:hidden!important;overflow-y:auto!important}
      body.dws-embedded .panel-header-actions,body.dws-embedded #load-button,body.dws-embedded #save-button{display:none!important}
      body.dws-embedded .status-bar{display:none!important}
      .dws-color-swatches{display:flex;flex-wrap:wrap;gap:7px;margin-top:2px;padding:8px;border:1px solid rgba(180,164,140,.35);border-radius:9px;background:rgba(8,10,11,.55)}
      .dws-color-swatch{width:29px;height:29px;padding:0;border:2px solid rgba(255,255,255,.24);border-radius:50%;background:var(--swatch);box-shadow:inset 0 0 0 1px rgba(0,0,0,.28),0 2px 7px rgba(0,0,0,.35);cursor:pointer}
      .dws-color-swatch:hover{transform:translateY(-1px);border-color:#fff}
      .dws-color-swatch.selected{border-color:#efc96d;box-shadow:0 0 0 3px rgba(225,184,87,.24),inset 0 0 0 1px rgba(0,0,0,.3)}
    `;
    document.head.appendChild(style);
  }
  document.addEventListener('input', (event) => {
    if (hydrating || event.target?.type === 'file') return;
    clearTimeout(dirtyTimer);
    dirtyTimer = setTimeout(() => post('rsdw-dirty', {}), 80);
    requestPreview();
  }, true);
  document.addEventListener('change', (event) => {
    if (hydrating || event.target?.type === 'file') return;
    if (event.target?.matches?.('[data-customization]')) {
      post('rsdw-appearance-change', { key: event.target.dataset.customization, value: event.target.value });
      decorateAppearanceControls(latestPalette);
    }
    clearTimeout(dirtyTimer);
    dirtyTimer = setTimeout(() => post('rsdw-dirty', {}), 80);
    requestPreview();
  }, true);
  document.addEventListener('keydown', (event) => {
    if ((event.ctrlKey || event.metaKey) && String(event.key).toLowerCase() === 's') {
      event.preventDefault();
      requestSave();
    }
  }, true);
  post('rsdw-ready', { href: location.href, hasCharacterInput: !!document.querySelector('#character-file') });
  const observer = new ResizeObserver(() => reportContentSize());
  observer.observe(document.querySelector('.item-editor-wrapper, .page-layout, main') || document.body);
  setTimeout(reportContentSize, 250);
});
