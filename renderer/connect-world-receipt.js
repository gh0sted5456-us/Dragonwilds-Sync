(() => {
  const modalRoot = document.getElementById('modal-root');
  if (!modalRoot) return;

  let stateRequest = null;

  const text = (value) => String(value ?? '').trim();
  const clientWorlds = (state) => Array.isArray(state?.client?.worlds) ? state.client.worlds : [];

  function receiptWorldName(receipt) {
    const button = receipt.querySelector('[data-copy-world-credential="worldName"]');
    return text(button?.closest('.world-credential-row')?.querySelector('code')?.textContent);
  }

  function findWorld(receipt, state) {
    const client = state?.client || {};
    const rows = clientWorlds(state);
    const activeId = text(client.active_world_id);
    if (activeId) {
      const active = rows.find((row) => text(row?.id) === activeId);
      if (active) return active;
    }
    const name = receiptWorldName(receipt).toLowerCase();
    if (!name) return null;
    return rows.find((row) => [row?.name, row?.nickname, row?.identity?.world_name]
      .some((value) => text(value).toLowerCase() === name)) || null;
  }

  function passwordState(world) {
    const password = text(world?.credentials?.password);
    if (password) return { value: password, copyable: true };

    const candidates = [
      world?.status?.password_required,
      world?.manifest_cache?.password_required,
      world?.password_required,
    ];
    const known = candidates.some((value) => typeof value === 'boolean');
    const required = candidates.some((value) => value === true);
    if (required) return { value: 'Password required · not saved', copyable: false };
    if (known) return { value: 'No password · Open World', copyable: false };
    return { value: 'Password status unavailable', copyable: false };
  }

  function classification(world) {
    const raw = world?.classification || world?.manifest_cache?.classification || {};
    const host = text(raw.host_type || raw.world_type || world?.kind || 'public').toLowerCase();
    const visibility = text(raw.visibility || '');
    const gameMode = text(raw.game_mode || raw.mode || 'normal').toLowerCase();
    const hostLabels = {
      singleplayer: 'Single Player',
      coop: 'Co-op Host',
      dedicated: 'Dedicated Server',
      public: 'Public World',
      server: 'Dedicated Server',
    };
    const modeLabels = {
      normal: 'Normal',
      hard: 'Hard Mode',
      hardcore: 'Hardcore',
      creative: 'Creative',
      custom: 'Custom',
    };
    return {
      worldType: `${hostLabels[host] || (host ? host.replace(/\b\w/g, (c) => c.toUpperCase()) : 'World')}${visibility ? ` · ${visibility.replace(/\b\w/g, (c) => c.toUpperCase())}` : ''}`,
      gameMode: modeLabels[gameMode] || gameMode.replace(/\b\w/g, (c) => c.toUpperCase()) || 'Normal',
    };
  }

  function detailRow(key, label, value) {
    const row = document.createElement('div');
    row.className = 'world-credential-row';
    row.dataset.dwsConnectionDetail = key;
    const wrap = document.createElement('div');
    const small = document.createElement('small');
    const code = document.createElement('code');
    small.textContent = label;
    code.textContent = value;
    wrap.append(small, code);
    row.append(wrap);
    return row;
  }

  function upsertDetail(receipt, key, label, value, beforeRow) {
    let row = receipt.querySelector(`[data-dws-connection-detail="${key}"]`);
    if (!row) {
      row = detailRow(key, label, value);
      receipt.insertBefore(row, beforeRow || receipt.querySelector('.world-credential-modes') || null);
    } else {
      const code = row.querySelector('code');
      if (code) code.textContent = value;
    }
  }

  function simplifyCopy(receipt, world) {
    const heading = receipt.querySelector('.world-credential-heading');
    if (heading) {
      const title = heading.querySelector('strong');
      const subtitle = heading.querySelector('small');
      if (title) title.textContent = 'World connection details';
      if (subtitle) subtitle.textContent = 'Use these details on the Dragonwilds Direct Connect screen if needed.';
      heading.querySelector('.status-pill')?.remove();
    }

    const passwordButton = receipt.querySelector('[data-copy-world-credential="password"]');
    const passwordRow = passwordButton?.closest('.world-credential-row');
    const passwordCode = passwordRow?.querySelector('code');
    const password = passwordState(world);
    if (passwordCode) passwordCode.textContent = password.value;
    if (passwordButton) passwordButton.disabled = !password.copyable;

    const types = classification(world);
    upsertDetail(receipt, 'world-type', 'World Type', types.worldType, passwordRow);
    upsertDetail(receipt, 'game-mode', 'Game Mode', types.gameMode, passwordRow);
    receipt.querySelector('.world-credential-modes')?.remove();

    const modal = receipt.closest('.modal, .desktop-window, [role="dialog"]') || receipt.parentElement;
    modal?.querySelectorAll('.identity-box p').forEach((paragraph) => {
      const current = text(paragraph.textContent);
      if (!/DragonLink-Connect|manual Direct Connect entry/i.test(current)) return;
      paragraph.textContent = current
        .replace(/This server opted into a one-time DragonLink-Connect handoff\.?/gi, 'Connection details are shown below.')
        .replace(/This server uses manual Direct Connect entry\.?/gi, 'Connection details are shown below.');
    });
  }

  async function freshState() {
    if (window.__DWSYNC_STATE__) return window.__DWSYNC_STATE__;
    if (!window.dragonwilds?.invoke) return null;
    if (!stateRequest) {
      stateRequest = window.dragonwilds.invoke('state.get', {})
        .then((value) => value?.state || value)
        .catch(() => null)
        .finally(() => { stateRequest = null; });
    }
    return stateRequest;
  }

  async function enhance(receipt) {
    const state = window.__DWSYNC_STATE__ || await freshState();
    const world = findWorld(receipt, state);
    if (!world) return;
    simplifyCopy(receipt, world);
  }

  function scan() {
    modalRoot.querySelectorAll('.world-credential-receipt').forEach((receipt) => { void enhance(receipt); });
  }

  new MutationObserver(scan).observe(modalRoot, { childList: true, subtree: true });
  window.addEventListener('dragonwilds:state-updated', scan);
  scan();
})();
