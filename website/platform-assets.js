/* Canonical baked platform-logo resolver for the public website. */
(() => {
  const baseCreateWorldCard = typeof createWorldCard === 'function' ? createWorldCard : null;
  if (!baseCreateWorldCard) return;

  const PLATFORMS = [
    { key: 'steam', label: 'Steam', src: 'assets/platforms/steam.svg', test: /\bsteam(?:cmd)?\b/i },
    { key: 'windows', label: 'Windows', src: 'assets/platforms/windows.svg', test: /\b(?:windows|win32|win64)\b/i },
    { key: 'xbox', label: 'Xbox', src: 'assets/platforms/xbox.svg', test: /\b(?:xbox|xbox live|xbox network)\b/i },
    { key: 'playstation', label: 'PlayStation', src: 'assets/platforms/playstation.svg', test: /\b(?:playstation|psn|ps4|ps5|playstation network)\b/i },
    { key: 'nintendo', label: 'Nintendo', src: 'assets/platforms/nintendo.svg', test: /\b(?:nintendo|nintendo switch|switch)\b/i },
    { key: 'epicgames', label: 'Epic Games', src: 'assets/platforms/epicgames.svg', test: /\b(?:epic|epic games|epicgames)\b/i },
    { key: 'linux', label: 'Linux', src: 'assets/platforms/linux.svg', test: /\blinux\b/i },
    { key: 'discord', label: 'Discord', src: 'assets/platforms/discord.svg', test: /\b(?:discord|rsdw)\b/i },
    { key: 'nexusmods', label: 'Nexus Mods', src: 'assets/platforms/nexusmods.svg', test: /\b(?:nexus|nexus mods|nexusmods)\b/i },
  ];

  const byLabel = (value) => PLATFORMS.find((entry) => entry.test.test(String(value || '').trim())) || null;

  window.DWS_PLATFORM_ASSETS = Object.freeze({
    list: PLATFORMS.map(({ key, label, src }) => Object.freeze({ key, label, src })),
    resolve(value) {
      const entry = byLabel(value);
      return entry ? { key: entry.key, label: entry.label, src: entry.src } : null;
    },
  });

  function makeLogo(entry, className = 'badge-icon badge-icon-asset badge-icon-brand') {
    const img = document.createElement('img');
    img.className = className;
    img.src = new URL(entry.src, document.baseURI).href;
    img.alt = '';
    img.decoding = 'async';
    img.loading = 'eager';
    img.dataset.platformKey = entry.key;
    img.addEventListener('error', () => {
      img.remove();
      console.warn(`[Dragonwilds Sync] Missing baked platform asset: ${entry.key} (${entry.src})`);
    }, { once: true });
    return img;
  }

  function repairBrandIcons(card) {
    card.querySelectorAll('.badge, .back-badge, .world-platform-badge').forEach((node) => {
      const entry = byLabel(node.textContent);
      if (!entry) return;
      const old = node.querySelector(':scope > .badge-icon, :scope > .metric-icon');
      if (old?.dataset?.platformKey === entry.key) return;
      old?.remove();
      node.prepend(makeLogo(entry));
      node.dataset.platformKey = entry.key;
    });
  }

  createWorldCard = function createWorldCardWithCanonicalPlatformAssets(world) {
    const card = baseCreateWorldCard(world);
    repairBrandIcons(card);
    return card;
  };

  // Preload every required baked asset once so failures are visible in the console
  // immediately instead of only after a particular badge happens to render.
  PLATFORMS.forEach((entry) => {
    const img = new Image();
    img.src = new URL(entry.src, document.baseURI).href;
    img.onerror = () => console.warn(`[Dragonwilds Sync] Required platform asset failed to preload: ${entry.key}`);
  });
})();
