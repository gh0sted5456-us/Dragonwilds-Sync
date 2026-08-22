(() => {
  'use strict';

  const text = (node) => String(node?.textContent || '').replace(/\s+/g, ' ').trim();

  function backgroundControl(root) {
    const direct = root.querySelector('#rsdw-avatar-background,[data-avatar-background]');
    if (direct) return direct.closest('label') || direct;
    return [...root.querySelectorAll('label')].find((label) => /^background\b/i.test(text(label))) || null;
  }

  function commonParent(nodes) {
    if (!nodes.length) return null;
    let parent = nodes[0].parentElement;
    while (parent && !nodes.every((node) => parent.contains(node))) parent = parent.parentElement;
    return parent;
  }

  function hotbarControl(root, background) {
    const direct = root.querySelector('.rsdw-character-hotbar,.character-hotbar,.studio-hotbar,[data-character-hotbar],[data-avatar-hotbar]');
    if (direct) return direct;
    const numbered = [...root.querySelectorAll('button')].filter((button) => /^\s*(?:[1-9]|10)\b/.test(text(button)) && !button.closest('nav'));
    const parent = commonParent(numbered);
    if (!parent || numbered.length < 4 || parent.contains(background)) return null;
    return parent;
  }

  function layoutCharacterEditor() {
    const webview = document.querySelector('#rsdw-avatar-webview');
    if (!webview) return;
    const editor = webview.closest('.rsdw-native-character-editor,.native-character-surface,.character-editor') || document;
    const background = backgroundControl(editor);
    const pose = [...editor.querySelectorAll('button,[role="tab"]')].find((node) => /^pose$/i.test(text(node)));
    if (background && pose) {
      const toolbar = pose.parentElement;
      background.classList.add('character-toolbar-background');
      if (background.parentElement !== toolbar || pose.nextElementSibling !== background) pose.insertAdjacentElement('afterend', background);
    }

    const hotbar = hotbarControl(editor, background);
    if (!hotbar) return;
    let dock = editor.querySelector(':scope .character-hotbar-dock');
    if (!dock) {
      dock = document.createElement('section');
      dock.className = 'character-hotbar-dock';
      dock.setAttribute('aria-label', 'Character hotbar');
      const preview = webview.closest('.rsdw-avatar-shell,.rsdw-preview-host,.character-preview-stage') || webview.parentElement;
      preview.insertAdjacentElement('afterend', dock);
    }
    hotbar.classList.add('character-hotbar-centered');
    if (hotbar.parentElement !== dock) dock.appendChild(hotbar);
  }

  function menuItemFamily(node) {
    const value = `${node.dataset.itemCategory || ''} ${node.dataset.itemEquipment || ''} ${node.dataset.itemCustom || ''} ${text(node)}`.toLowerCase();
    if (node.dataset.itemCustom === '1' || /modded|custom/.test(value)) return 'modded';
    if (/weapon|sword|bow|staff|axe|pick|hand/.test(value)) return 'weapons';
    if (/attachment|cape|jewel|ring|amulet/.test(value)) return 'attachments';
    if (/armou?r|head|body|legs|helmet|chest|robe/.test(value)) return 'armour';
    return 'other';
  }

  function enhanceItemMenu(menu) {
    if (!menu || menu.dataset.filteredItemMenu === '1') return;
    menu.dataset.filteredItemMenu = '1';
    [...menu.querySelectorAll('button,a')].filter((node) => /browse all compatible items/i.test(text(node))).forEach((node) => node.remove());
    const controls = document.createElement('div'); controls.className = 'character-item-menu-filters';
    controls.innerHTML = `<label><span>Search</span><input type="search" placeholder="Filter items…" data-character-item-query/></label><div role="group" aria-label="Item filters">${['all','weapons','armour','attachments','modded'].map((value) => `<button type="button" data-character-item-filter="${value}" class="${value === 'all' ? 'active' : ''}">${value[0].toUpperCase() + value.slice(1)}</button>`).join('')}</div>`;
    const list = menu.querySelector('.character-equipment-menu-items,[data-item-repository-list]') || menu; menu.insertBefore(controls, list);
    let family = 'all';
    const apply = () => { const query = String(controls.querySelector('[data-character-item-query]').value || '').trim().toLowerCase(); [...list.querySelectorAll('[data-character-equip-item],[data-item-data],button')].forEach((node) => { if (node.closest('.character-item-menu-filters')) return; node.hidden = !((family === 'all' || menuItemFamily(node) === family) && (!query || text(node).toLowerCase().includes(query))); }); };
    controls.addEventListener('input', apply);
    controls.addEventListener('click', (event) => { const button = event.target.closest('[data-character-item-filter]'); if (!button) return; family = button.dataset.characterItemFilter; controls.querySelectorAll('[data-character-item-filter]').forEach((node) => node.classList.toggle('active', node === button)); apply(); });
  }

  const slotSelector = '.character-equipment-socket,[data-character-equipment-slot],[data-rsdw-preview-slot],.character-action-bar button,[data-character-action-slot]';
  document.addEventListener('click', (event) => {
    const slot = event.target.closest?.(slotSelector); if (!slot || slot.closest('.character-equipment-context-menu,.character-hotbar-context-menu')) return;
    if (slot.dataset.allowRepositoryClick === '1') { delete slot.dataset.allowRepositoryClick; return; }
    event.preventDefault(); event.stopPropagation(); event.stopImmediatePropagation();
  }, true);
  function enhanceCharacterMenus() {
    document.querySelectorAll('.character-equipment-context-menu:not([data-filtered-item-menu])').forEach(enhanceItemMenu);
  }

  let scheduled = false;
  const schedule = () => {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => { scheduled = false; layoutCharacterEditor(); enhanceCharacterMenus(); });
  };

  new MutationObserver(schedule).observe(document.documentElement, { childList: true, subtree: true });
  window.addEventListener('dragonwilds:state-updated', schedule);
  schedule();
})();
