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
      const label = mod.delivery === 'external' ? `External · ${statusLabel(mod.status)}` : 'Server';
      if (button.textContent !== label) button.textContent = label;
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
    decorateSetupButton();
    document.querySelectorAll('.mod-row').forEach((row) => void decorateRow(row));
  }

  function decorateSetupButton() {
    document.querySelectorAll('.server-shell-card[data-server-profile-id] .server-tabs').forEach((tabs) => {
      if (tabs.querySelector('[data-delivery-setup]')) return;
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'btn ghost';
      button.dataset.deliverySetup = '1';
      button.textContent = 'File Sharing Setup';
      button.addEventListener('click', async () => {
        try { await openSetup(await activeProfileId(tabs)); }
        catch (error) { window.alert(error?.message || String(error)); }
      });
      tabs.appendChild(button);
    });
  }

  async function openSetup(profileId) {
    if (!profileId) throw new Error('Select a hosted World first.');
    let payload = await loadMods(profileId, true);
    const dialog = document.createElement('dialog');
    dialog.className = 'external-hosting-dialog';
    dialog.innerHTML = `<form method="dialog" class="external-hosting-card">
      <header><div><div class="external-hosting-eyebrow">World file delivery</div><h2>File Sharing Setup</h2><p>Direct server, cloud download, or hybrid fallback</p></div><button value="cancel" class="external-hosting-close" aria-label="Close">×</button></header>
      <div class="external-hosting-help">Clients receive the World manifest, download inside Sync, verify the files, and report parity before joining. Each required mod can use its own file source.</div>
      <ol class="external-hosting-steps"><li><b>Prepare files</b> — generate verified ZIPs and a handoff manifest for all client-required mods.</li><li><b>Upload or sync the folder</b> — place the generated folder in Google Drive, OneDrive, Dropbox, or an HTTPS host. Enable public file downloads.</li><li><b>Link and verify</b> — choose Configure beside each mod, paste its public ZIP link, then Test Link. Enable fallback for hybrid delivery.</li></ol>
      <div class="external-hosting-help"><b>Cloud account setup</b><br>Google Drive: share each ZIP as Anyone with the link / Viewer. OneDrive: use Anyone with the link and allow downloads. Dropbox: create a view-only file link. Folder links alone do not identify downloadable packages; Sync needs each ZIP's file link. Cloud sign-in and automatic upload require registered provider accounts and are not enabled in this build.</div>
      <div data-delivery-summary role="status"></div><div data-delivery-rows></div>
      <div class="external-hosting-result" data-delivery-result role="status"></div>
      <footer><button type="button" data-delivery-prepare>Prepare All Packages</button><button type="button" data-delivery-folder>Open Package Folder</button><button type="button" data-delivery-refresh>Refresh Status</button><span class="spacer"></span><button value="cancel">Close</button></footer>
    </form>`;
    document.body.appendChild(dialog);
    const result = dialog.querySelector('[data-delivery-result]');
    const prepare = dialog.querySelector('[data-delivery-prepare]');
    const rows = dialog.querySelector('[data-delivery-rows]');
    function render() {
      const mods = payload.mods || [];
      const cloud = mods.filter((mod) => mod.delivery === 'external');
      const ready = cloud.filter((mod) => mod.status === 'ready').length;
      dialog.querySelector('[data-delivery-summary]').textContent = `${mods.length} required mods · ${mods.length - cloud.length} direct · ${ready}/${cloud.length} cloud sources verified`;
      rows.innerHTML = mods.map((mod) => `<div class="external-hosting-setup-row"><div><strong>${esc(mod.name)}</strong><small>${esc(mod.family)} · ${esc(bytes(mod.size))} · ${esc(statusLabel(mod.status))}</small></div><button type="button" data-delivery-mod="${esc(mod.key)}">Configure</button></div>`).join('') || '<p>No client-required mods selected. Choose Client or Both on the Mods tab first.</p>';
      rows.querySelectorAll('[data-delivery-mod]').forEach((button) => button.addEventListener('click', () => {
        openDialog(profileId, button.dataset.deliveryMod).catch((error) => showResult(result, error.message, 'error'));
      }));
    }
    prepare.addEventListener('click', async () => {
      prepare.disabled = true;
      showResult(result, 'Preparing packages and hashes…');
      try {
        const response = await bridge.invoke('server.external_mod.prepare_folder', { id: profileId });
        invalidate(); payload = await loadMods(profileId, true); render();
        showResult(result, `${response.packages.length} package(s) prepared. ${response.errors.length ? response.errors.map((row) => `${row.name}: ${row.error}`).join('; ') : 'Open the folder, upload its contents, then configure and verify each public file link.'}`, response.ok ? 'ok' : 'error');
      } catch (error) { showResult(result, error.message, 'error'); }
      finally { prepare.disabled = false; }
    });
    dialog.querySelector('[data-delivery-folder]').addEventListener('click', async () => {
      try { await bridge.openPath(payload.export_root); }
      catch (error) { showResult(result, error.message, 'error'); }
    });
    dialog.querySelector('[data-delivery-refresh]').addEventListener('click', async () => {
      try { invalidate(); payload = await loadMods(profileId, true); render(); }
      catch (error) { showResult(result, error.message, 'error'); }
    });
    render();
    dialog.addEventListener('close', () => dialog.remove(), { once: true });
    dialog.showModal();
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
