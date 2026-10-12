(() => {
  'use strict';

  const bridge = window.dragonwilds;
  if (!bridge?.invoke) return;

  const CACHE_MS = 2500;
  let cachedProfile = '';
  let cachedAt = 0;
  let cachedPayload = null;
  let refreshTimer = 0;

  const text = (value) => String(value ?? '').trim();
  const esc = (value) => String(value ?? '')
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#39;');

  function bytes(value) {
    const size = Math.max(0, Number(value || 0));
    if (size < 1024) return `${size} B`;
    const units = ['KB', 'MB', 'GB', 'TB'];
    let amount = size / 1024;
    let unit = units[0];
    for (let index = 1; index < units.length && amount >= 1024; index += 1) {
      amount /= 1024;
      unit = units[index];
    }
    return `${amount >= 100 ? amount.toFixed(0) : amount >= 10 ? amount.toFixed(1) : amount.toFixed(2)} ${unit}`;
  }

  function statusLabel(status) {
    return ({
      server: 'SERVER', ready: 'READY', needs_package: 'NEEDS PACKAGE',
      needs_link: 'NEEDS LINK', untested: 'TEST LINK', outdated: 'OUTDATED',
    })[text(status).toLowerCase()] || text(status || 'SERVER').toUpperCase();
  }

  async function stateSnapshot() {
    if (window.__DWSYNC_STATE__ && typeof window.__DWSYNC_STATE__ === 'object') return window.__DWSYNC_STATE__;
    return bridge.invoke('state.get', {});
  }

  async function activeProfileId(row = null) {
    const direct = text(
      row?.dataset?.worldId || row?.dataset?.serverWorldId || row?.dataset?.serverProfileId ||
      row?.closest?.('[data-world-id]')?.dataset?.worldId ||
      row?.closest?.('[data-server-world-id]')?.dataset?.serverWorldId ||
      row?.closest?.('[data-server-profile-id]')?.dataset?.serverProfileId
    );
    if (direct) return direct;
    const state = await stateSnapshot();
    return text(state?.server?.active_world_id || state?.server?.runtime?.active_profile_id || state?.server_profiles?.[0]?.id);
  }

  async function loadMods(profileId, force = false) {
    const now = Date.now();
    if (!force && cachedPayload && cachedProfile === profileId && now - cachedAt < CACHE_MS) return cachedPayload;
    const payload = await bridge.invoke('server.external_mod.list', { id: profileId });
    cachedProfile = profileId;
    cachedAt = now;
    cachedPayload = payload || { mods: [] };
    return cachedPayload;
  }

  function invalidate() {
    cachedAt = 0;
    cachedPayload = null;
  }

  function keyFromRow(row) {
    const marker = row?.querySelector?.('[data-mod-tags]') || (row?.matches?.('[data-mod-tags]') ? row : null);
    return text(marker?.dataset?.modTags || row?.dataset?.modTags);
  }

  function findMod(payload, key) {
    return (payload?.mods || []).find((row) => text(row?.key) === key) || null;
  }

  async function decorateRow(row) {
    if (!row || row.dataset.externalHostingDecorating === '1') return;
    const key = keyFromRow(row);
    if (!key || !/^(ue4ss_mod|runeschema_mod|pak_mod)::/i.test(key)) return;
    row.dataset.externalHostingDecorating = '1';
    try {
      const profileId = await activeProfileId(row);
      if (!profileId) return;
      const payload = await loadMods(profileId);
      const mod = findMod(payload, key);
      if (!mod) return;
      let button = row.querySelector('[data-external-hosting-open]');
      if (!button) {
        button = document.createElement('button');
        button.type = 'button';
        button.className = 'external-hosting-pill';
        button.dataset.externalHostingOpen = key;
        button.addEventListener('click', (event) => {
          event.preventDefault();
          event.stopPropagation();
          openDialog(profileId, key).catch((error) => window.alert(error?.message || String(error)));
        });
        const actions = row.querySelector('.mod-actions,.row-actions,.actions') || row;
        actions.appendChild(button);
      }
      button.dataset.delivery = mod.delivery || 'server';
      button.dataset.status = mod.status || 'server';
      button.textContent = mod.delivery === 'external' ? `External · ${statusLabel(mod.status)}` : 'Server';
      button.title = mod.delivery === 'external'
        ? `${mod.name} uses external delivery. Dragonwilds Sync still verifies it against the World manifest.`
        : `${mod.name} downloads normally from the World host.`;
    } catch (_) {
      // Older backends simply omit the control; normal Sync remains untouched.
    } finally {
      row.dataset.externalHostingDecorating = '0';
    }
  }

  function decorateAll() {
    document.querySelectorAll('.mod-row').forEach((row) => void decorateRow(row));
  }

  function scheduleDecorate() {
    clearTimeout(refreshTimer);
    refreshTimer = setTimeout(decorateAll, 80);
  }

  function showResult(node, message, kind = '') {
    node.textContent = message;
    node.dataset.kind = kind;
  }

  async function openDialog(profileId, key) {
    const payload = await loadMods(profileId, true);
    let mod = findMod(payload, key);
    if (!mod) throw new Error('This mod is no longer available in the selected World.');

    const dialog = document.createElement('dialog');
    dialog.className = 'external-hosting-dialog';
    dialog.innerHTML = `
      <form method="dialog" class="external-hosting-card">
        <header>
          <div>
            <div class="external-hosting-eyebrow">External Mod Hosting</div>
            <h2>${esc(mod.name)}</h2>
            <p>${esc(mod.family)} · ${esc(bytes(mod.size))}</p>
          </div>
          <button value="cancel" class="external-hosting-close" aria-label="Close">×</button>
        </header>
        <div class="external-hosting-help">Small mods can stay on <b>Server</b>. Use <b>External</b> for a large mod you want players to download from Google Drive, OneDrive, Dropbox, or another public HTTPS link. Sync still checks every file against the World manifest.</div>
        <label>Delivery
          <select data-external-delivery>
            <option value="server">Server</option>
            <option value="external">External</option>
          </select>
        </label>
        <div data-external-fields>
          <label>Provider
            <select data-external-provider>
              <option value="auto">Auto-detect</option>
              <option value="google_drive">Google Drive</option>
              <option value="onedrive">OneDrive</option>
              <option value="dropbox">Dropbox</option>
              <option value="direct_https">Direct HTTPS</option>
            </select>
          </label>
          <label>Public download link
            <input data-external-url type="url" spellcheck="false" placeholder="https://..." />
          </label>
          <label class="external-hosting-check"><input data-external-fallback type="checkbox" /> Fall back to the World host if the external download fails</label>
          <div class="external-hosting-package">
            <div><span>Status</span><b data-external-status></b></div>
            <div><span>Prepared package</span><b data-external-archive></b></div>
            <div class="external-hosting-path" data-external-path></div>
          </div>
        </div>
        <div class="external-hosting-result" data-external-result role="status"></div>
        <footer>
          <button type="button" data-external-prepare>Prepare Package</button>
          <button type="button" data-external-test>Test Link</button>
          <span class="spacer"></span>
          <button type="button" data-external-save class="primary">Save</button>
          <button value="cancel">Close</button>
        </footer>
      </form>`;
    document.body.appendChild(dialog);

    const delivery = dialog.querySelector('[data-external-delivery]');
    const provider = dialog.querySelector('[data-external-provider]');
    const url = dialog.querySelector('[data-external-url]');
    const fallback = dialog.querySelector('[data-external-fallback]');
    const fields = dialog.querySelector('[data-external-fields]');
    const status = dialog.querySelector('[data-external-status]');
    const archive = dialog.querySelector('[data-external-archive]');
    const path = dialog.querySelector('[data-external-path]');
    const result = dialog.querySelector('[data-external-result]');
    const prepare = dialog.querySelector('[data-external-prepare]');
    const test = dialog.querySelector('[data-external-test]');
    const save = dialog.querySelector('[data-external-save]');

    function render() {
      delivery.value = mod.delivery || 'server';
      provider.value = mod.provider || 'auto';
      url.value = mod.url || '';
      fallback.checked = mod.fallback_to_server !== false;
      fields.hidden = delivery.value !== 'external';
      prepare.hidden = delivery.value !== 'external';
      test.hidden = delivery.value !== 'external';
      status.textContent = statusLabel(mod.status);
      status.dataset.status = mod.status || 'server';
      archive.textContent = mod.archive_size ? `${mod.archive_path?.split(/[\\/]/).pop() || 'package.zip'} · ${bytes(mod.archive_size)}` : 'Not prepared';
      path.textContent = mod.archive_path || '';
      path.title = mod.archive_path || '';
    }

    async function saveConfig(message = 'Saved.') {
      showResult(result, 'Saving…');
      mod = await bridge.invoke('server.external_mod.configure', {
        id: profileId, key, delivery: delivery.value, provider: provider.value,
        url: url.value.trim(), fallback_to_server: fallback.checked,
      });
      invalidate();
      render();
      showResult(result, message, 'ok');
      scheduleDecorate();
      return mod;
    }

    delivery.addEventListener('change', () => {
      fields.hidden = delivery.value !== 'external';
      prepare.hidden = fields.hidden;
      test.hidden = fields.hidden;
    });
    save.addEventListener('click', () => void saveConfig().catch((error) => showResult(result, error?.message || String(error), 'error')));
    prepare.addEventListener('click', async () => {
      try {
        if (delivery.value !== 'external') delivery.value = 'external';
        await saveConfig('Preparing package…');
        mod = await bridge.invoke('server.external_mod.prepare', { id: profileId, key });
        invalidate(); render(); scheduleDecorate();
        showResult(result, `Package ready. Upload ${mod.archive_path?.split(/[\\/]/).pop() || 'the ZIP'} to your provider, then paste its public link here.`, 'ok');
      } catch (error) { showResult(result, error?.message || String(error), 'error'); }
    });
    test.addEventListener('click', async () => {
      try {
        await saveConfig('Testing and verifying the uploaded package…');
        const response = await bridge.invoke('server.external_mod.test', { id: profileId, key });
        mod = response?.mod || mod;
        invalidate(); render(); scheduleDecorate();
        showResult(result, response?.ok ? 'Uploaded package matches. Publish the World when ready.' : (response?.error || 'Link test failed.'), response?.ok ? 'ok' : 'error');
      } catch (error) { showResult(result, error?.message || String(error), 'error'); }
    });

    render();
    dialog.addEventListener('close', () => dialog.remove(), { once: true });
    dialog.showModal();
  }

  const observer = new MutationObserver(scheduleDecorate);
  observer.observe(document.getElementById('app') || document.body, { childList: true, subtree: true });
  document.addEventListener('dws:state-updated', () => { invalidate(); scheduleDecorate(); });
  scheduleDecorate();
})();
