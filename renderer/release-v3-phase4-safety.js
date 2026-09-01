(() => {
  'use strict';
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (ch) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));

  function sourcePlacard(id) {
    return [...document.querySelectorAll(`.v3p4-placard[data-world-id="${CSS.escape(String(id||''))}"]`)]
      .find((node) => !node.closest('.v3p4-window')) || null;
  }

  function stabilizeWindow(host) {
    if (!host || host.dataset.v3p4Safety === '1') return;
    const id = String(host.dataset.v3p4Window || '').trim();
    const card = host.querySelector('.v3p4-window-body > .world-card');
    const source = sourcePlacard(id);
    if (!id || !card || !source) return;
    const back = source.querySelector('.v3p4-back');
    if (!back) return;

    const summary = card.querySelector('.v3p4-window-summary')?.cloneNode(true) || document.createElement('div');
    const front = document.createElement('div');
    front.className = 'v3p4-face v3p4-front';
    front.appendChild(summary);
    const controls = document.createElement('div');
    controls.className = 'v3p4-page-controls';
    controls.innerHTML = '<span data-v3p4-page-status>Page 1 / 2</span><span class="card-flip-hint" aria-hidden="true">CLICK CARD · DETAILS ↻</span>';
    front.appendChild(controls);

    const inner = document.createElement('div');
    inner.className = 'v3p4-inner';
    inner.append(front, back.cloneNode(true));
    card.replaceChildren(inner);
    card.classList.add('v3p4-placard');
    card.dataset.v3p4Decorated = '1';
    card.tabIndex = 0;
    host.dataset.v3p4Safety = '1';
  }

  function addWindowAction(menu, row) {
    if (!menu || !row || menu.querySelector('[data-v3p4-safe-window-open]')) return;
    const id = String(row.dataset.worldId || '').trim();
    if (!id) return;
    const button = document.createElement('button');
    button.className = 'context-menu-item';
    button.dataset.v3p4SafeWindowOpen = id;
    button.textContent = 'Open in Window';
    const openPlacard = menu.querySelector('[data-v3p4-open-menu]');
    if (openPlacard) openPlacard.insertAdjacentElement('afterend', button);
    else menu.prepend(button);
  }

  // This capture listener runs after the Phase 4 flip listener. It prevents the
  // older card-body click handler from also navigating into Manage/Details.
  document.addEventListener('click', (event) => {
    const windowButton = event.target.closest('[data-v3p4-safe-window-open]');
    if (windowButton) {
      event.preventDefault();
      event.stopPropagation();
      document.querySelector('.world-context-menu')?.remove();
      window.__DWSYNC_V3_PHASE4__?.openPlacard?.(windowButton.dataset.v3p4SafeWindowOpen);
      return;
    }
    const card = event.target.closest('.v3p4-placard[data-world-id]');
    if (!card || event.target.closest('button,a,input,select,textarea,.v3p4-back-scroll')) return;
    event.preventDefault();
    event.stopPropagation();
  }, true);

  document.addEventListener('contextmenu', (event) => {
    const row = event.target.closest('.world-list-row[data-world-id]');
    if (!row) return;
    setTimeout(() => addWindowAction(document.querySelector('.world-context-menu'), row), 0);
  });

  const observer = new MutationObserver(() => {
    document.querySelectorAll('.v3p4-window:not([data-v3p4-safety="1"])').forEach(stabilizeWindow);
  });
  observer.observe(document.documentElement, {childList:true, subtree:true});
  document.querySelectorAll('.v3p4-window').forEach(stabilizeWindow);
})();
