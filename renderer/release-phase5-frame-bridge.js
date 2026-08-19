(() => {
  'use strict';
  const query = new URLSearchParams(window.location.search);
  if (query.get('phase5Internal') !== '1' || window.parent === window || window.dragonwilds) return;
  try {
    // Application-owned route workspaces are same-origin frames inside the one
    // Dragonwilds Sync renderer window. Reuse the parent preload bridge rather
    // than creating another Electron BrowserWindow/backend process surface.
    if (window.parent?.dragonwilds) window.dragonwilds = window.parent.dragonwilds;
  } catch (_) {
    // app.js will surface the normal backend-unavailable state if the parent
    // bridge cannot be inherited for any reason.
  }
})();
