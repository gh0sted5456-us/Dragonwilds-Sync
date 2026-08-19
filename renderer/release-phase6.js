(() => {
  'use strict';

  const api = window.dragonwilds;
  if (!api?.invoke) return;

  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (ch) => ({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  }[ch]));

  let opening = false;
  let sequence = 0;

  function navButton() {
    return `<button type="button" data-phase6-settings-community><span>⌂</span>Community</button>`;
  }

  function setMessage(host, text, kind='') {
    const node = host?.querySelector('[data-phase6-community-status]');
    if (!node) return;
    node.textContent = text;
    node.dataset.kind = kind;
  }

  function communityRow(row = {}) {
    const id = String(row.id || `community-${Date.now()}-${Math.random().toString(16).slice(2)}`);
    return `<article class="phase6-community-row" data-phase6-community-row data-community-id="${esc(id)}">
      <div class="phase6-community-row-head">
        <label class="phase6-community-enabled"><input type="checkbox" data-community-enabled ${row.enabled === false ? '' : 'checked'} /> Enabled</label>
        <button class="btn ghost compact-btn" type="button" data-community-remove>Remove</button>
      </div>
      <div class="form-grid">
        <label class="form-group"><span>Name</span><input class="field" data-community-name maxlength="120" value="${esc(row.name || 'Community')}" /></label>
        <label class="form-group"><span>Website</span><input class="field" data-community-website value="${esc(row.website_url || '')}" placeholder="https://community.example/" /></label>
        <label class="form-group full"><span>World manifest / directory URL</span><input class="field" data-community-worlds value="${esc(row.worlds_url || '')}" placeholder="https://community.example/worlds.json" /></label>
        <label class="form-group full"><span>Recommended mods manifest URL</span><input class="field" data-community-recommendations value="${esc(row.recommendations_url || '')}" placeholder="https://community.example/mods.json" /></label>
        <label class="form-group full"><span>Icon URL</span><input class="field" data-community-icon value="${esc(row.icon_url || '')}" placeholder="https://community.example/icon.png" /></label>
      </div>
    </article>`;
  }

  function collect(host) {
    return [...host.querySelectorAll('[data-phase6-community-row]')].map((node) => ({
      id: node.dataset.communityId || '',
      name: node.querySelector('[data-community-name]')?.value.trim() || 'Community',
      enabled: !!node.querySelector('[data-community-enabled]')?.checked,
      worlds_url: node.querySelector('[data-community-worlds]')?.value.trim() || '',
      recommendations_url: node.querySelector('[data-community-recommendations]')?.value.trim() || '',
      website_url: node.querySelector('[data-community-website]')?.value.trim() || '',
      icon_url: node.querySelector('[data-community-icon]')?.value.trim() || '',
    }));
  }

  async function save(host, quiet=false) {
    const communities = collect(host);
    const response = await api.invoke('application.communities.settings', { communities });
    if (!quiet) setMessage(host, `${response?.communities?.length ?? communities.length} Community source${communities.length === 1 ? '' : 's'} saved locally.`, 'ok');
    return response;
  }

  function bindRows(host) {
    host.querySelectorAll('[data-community-remove]').forEach((button) => {
      if (button.dataset.phase6Bound) return;
      button.dataset.phase6Bound = '1';
      button.addEventListener('click', () => button.closest('[data-phase6-community-row]')?.remove());
    });
  }

  function renderRows(host, rows) {
    const list = host.querySelector('[data-phase6-community-list]');
    if (!list) return;
    list.innerHTML = (rows || []).map(communityRow).join('') || '<div class="empty-state">No Community manifest hosts are configured yet. Add one below; local World Management still works normally while this list is empty or offline.</div>';
    bindRows(host);
  }

  async function hydrate(host, token) {
    try {
      const [community, integration] = await Promise.all([
        api.invoke('application.communities.list', {}),
        api.invoke('application.phase6.status', {}),
      ]);
      if (token !== sequence || !host.isConnected) return;
      renderRows(host, community?.communities || []);
      const phase6 = integration?.phase6 || {};
      const dc = phase6.dragonconnect || {};
      const sync = phase6.sync?.last_completed || {};
      const vault = phase6.secret_store || {};
      const summary = host.querySelector('[data-phase6-integration-summary]');
      if (summary) summary.innerHTML = `
        <div><strong>DragonConnect</strong><span>${esc(dc.status || (dc.installed ? 'installed' : 'not installed'))}${dc.available_version ? ` · ${esc(dc.available_version)}` : ''}</span></div>
        <div><strong>Last verified Sync</strong><span>${sync.world_id ? `${esc(sync.world_id)} · ${esc(sync.transfer_gate || sync.status || 'verified')}` : 'No verified remote Sync yet'}</span></div>
        <div><strong>Credential storage</strong><span>Encrypted local references · ${Number(vault.entry_count || 0)} stored value${Number(vault.entry_count || 0) === 1 ? '' : 's'}</span></div>`;
      setMessage(host, 'Cached Community state loaded. Refresh is explicit and each source may fail independently.', 'ok');
    } catch (error) {
      if (token === sequence) setMessage(host, `Community state could not be loaded: ${error.message}`, 'error');
    }
  }

  async function openCommunity(button) {
    if (opening) return;
    const nav = button.closest('.settings-nav');
    const layout = nav?.closest('.settings-layout');
    const content = layout ? [...layout.children].find((child) => child !== nav) : null;
    if (!nav || !content) return;
    opening = true;
    try {
      nav.querySelectorAll('button').forEach((item) => item.classList.toggle('active', item === button));
      const token = ++sequence;
      content.innerHTML = `<div class="phase6-community-page">
        <div class="page-header phase6-community-header"><div><div class="eyebrow">Settings</div><h1>Community</h1><div class="page-subtitle">Configure independent Community World-directory and recommended-mod manifest hosts. Cached local state opens first; remote refresh is always explicit.</div></div><div class="header-actions"><button class="btn ghost" type="button" data-community-direct>Direct Connect</button><button class="btn ghost" type="button" data-community-worlds>Open Worlds</button><button class="btn primary" type="button" data-community-refresh>Refresh Sources</button></div></div>
        <section class="settings-section"><div class="panel-header"><div><h2>Community Manifest Hosts</h2><div class="panel-subtitle">A failed/offline source never blocks another source or your cached local view.</div></div><button class="btn ghost compact-btn" type="button" data-community-add>+ Add Community</button></div><div class="phase6-community-list" data-phase6-community-list><div class="phase6-community-loading">Loading cached Community state…</div></div><div class="header-actions phase6-community-save"><button class="btn primary" type="button" data-community-save>Save Community Sources</button></div></section>
        <section class="settings-section"><h2>Final Integration State</h2><div class="phase6-integration-summary" data-phase6-integration-summary><div><strong>DragonConnect</strong><span>Checking local managed state…</span></div><div><strong>Last verified Sync</strong><span>Checking journal…</span></div><div><strong>Credential storage</strong><span>Checking local reference vault…</span></div></div><div class="identity-box"><strong>Source ownership</strong><p><b>RSDWTools</b> supplies icons/item/reference data. <b>RSDW Toolkit / DevKit</b> is the UE4SS runtime tooling mod. <b>DragonConnect</b> is the hidden CLIENT handoff component; its physical <code>PersistentDirectConnectIP</code> identity remains only for compatibility.</p></div></section>
        <div class="panel-subtitle phase6-community-status" data-phase6-community-status>Loading cached Community state…</div>
      </div>`;

      content.querySelector('[data-community-add]')?.addEventListener('click', () => {
        const list = content.querySelector('[data-phase6-community-list]');
        if (!list) return;
        if (list.querySelector('.empty-state')) list.innerHTML = '';
        list.insertAdjacentHTML('beforeend', communityRow({}));
        bindRows(content);
      });
      content.querySelector('[data-community-save]')?.addEventListener('click', async () => {
        try { setMessage(content, 'Saving Community sources…'); await save(content); }
        catch (error) { setMessage(content, error.message || String(error), 'error'); }
      });
      content.querySelector('[data-community-refresh]')?.addEventListener('click', async () => {
        try {
          setMessage(content, 'Saving local settings, then refreshing configured sources…');
          await save(content, true);
          const refreshed = await api.invoke('application.communities.refresh', {});
          const result = refreshed?.result || {};
          setMessage(content, result.ok ? 'Community sources refreshed.' : (result.partial ? `Refresh completed with partial source errors: ${(result.errors || []).join(' · ')}` : `Community refresh failed: ${(result.errors || []).join(' · ')}`), result.ok ? 'ok' : 'error');
          const latest = await api.invoke('application.communities.list', {});
          renderRows(content, latest?.communities || collect(content));
        } catch (error) { setMessage(content, error.message || String(error), 'error'); }
      });
      const openWorlds = (direct=false) => {
        const worlds = document.querySelector('[data-route="worlds"], [data-nav-route="worlds"]');
        worlds?.click();
        if (direct) setTimeout(() => document.querySelector('#add-world-card')?.click(), 80);
      };
      content.querySelector('[data-community-worlds]')?.addEventListener('click', () => openWorlds(false));
      content.querySelector('[data-community-direct]')?.addEventListener('click', () => openWorlds(true));
      hydrate(content, token);
    } finally {
      opening = false;
    }
  }

  function enhance() {
    const nav = document.querySelector('.settings-layout .settings-nav');
    if (!nav || nav.querySelector('[data-phase6-settings-community]')) return;
    const marker = nav.querySelector('[data-settings-tab="about"]');
    if (marker) marker.insertAdjacentHTML('beforebegin', navButton());
    else nav.insertAdjacentHTML('beforeend', navButton());
    nav.querySelector('[data-phase6-settings-community]')?.addEventListener('click', (event) => openCommunity(event.currentTarget));
  }

  let scheduled = false;
  const schedule = () => {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => { scheduled = false; enhance(); });
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', schedule, { once:true });
  else schedule();
  new MutationObserver(schedule).observe(document.documentElement, { childList:true, subtree:true });
})();
