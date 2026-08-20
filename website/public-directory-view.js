/* Public Server Directory view mode + application-link helper. */
(() => {
  const VIEW_KEY = 'dragonwilds-sync-public-directory-view';
  const PAGE_LINK = 'https://gh0sted5456-us.github.io/Dragonwilds-Sync/servers.html';
  const grid = document.querySelector('#world-grid');
  if (!grid) return;

  const buttons = [...document.querySelectorAll('[data-directory-view]')];
  const normalizeView = (value) => value === 'horizontal' ? 'horizontal' : 'placards';
  let view = normalizeView(localStorage.getItem(VIEW_KEY));

  function applyView() {
    grid.classList.toggle('directory-horizontal', view === 'horizontal');
    buttons.forEach((button) => {
      const active = normalizeView(button.dataset.directoryView) === view;
      button.setAttribute('aria-pressed', String(active));
    });
  }

  buttons.forEach((button) => button.addEventListener('click', () => {
    view = normalizeView(button.dataset.directoryView);
    localStorage.setItem(VIEW_KEY, view);
    applyView();
  }));

  const copyButton = document.querySelector('#copy-app-directory-link');
  const copyStatus = document.querySelector('#copy-app-directory-status');
  copyButton?.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(PAGE_LINK);
      copyButton.textContent = 'Copied ✓';
      if (copyStatus) copyStatus.textContent = 'Paste this webpage link into Dragonwilds Sync → Public Server List.';
      setTimeout(() => { copyButton.textContent = 'Copy App Link'; }, 1800);
    } catch (_) {
      if (copyStatus) copyStatus.textContent = PAGE_LINK;
    }
  });

  applyView();
})();
