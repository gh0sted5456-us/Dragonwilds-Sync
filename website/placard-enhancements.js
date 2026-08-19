/* Icon and motion enhancements layered over the app-parity World placards. */
(() => {
  const SVG_NS = 'http://www.w3.org/2000/svg';
  const baseCreateWorldCard = createWorldCard;

  const platformAssets = {
    steam: 'steam.svg', windows: 'windows.svg', linux: 'linux.svg', discord: 'discord.svg',
    xbox: 'xbox.svg', playstation: 'playstation.svg', nintendo: 'nintendo.svg', epic: 'epicgames.svg',
  };

  const svgPaths = {
    shield: ['M12 2 20 5v6c0 5.2-3.4 9.3-8 11-4.6-1.7-8-5.8-8-11V5l8-3Z'],
    game: ['M7 7h10l2 5-2 5-3-2H10l-3 2-2-5 2-5Z', 'M8 12h4', 'M10 10v4', 'M15.5 11.5h.01', 'M17 13.5h.01'],
    server: ['M5 4h14v5H5z', 'M5 15h14v5H5z', 'M8 6.5h.01', 'M8 17.5h.01', 'M11 6.5h5', 'M11 17.5h5'],
    rune: ['M12 2 20 8l-3 11H7L4 8l8-6Z', 'M9 8l6 8', 'M15 8l-6 8'],
    code: ['M9 7 4 12l5 5', 'M15 7l5 5-5 5'],
    package: ['M4 7 12 3l8 4-8 4-8-4Z', 'M4 7v10l8 4 8-4V7', 'M12 11v10'],
    verified: ['M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Z', 'm8 12 2.5 2.5L16 9'],
    badge: ['M12 3 15 8l6 1-4 4 .8 6L12 16l-5.8 3L7 13 3 9l6-1 3-5Z'],
    cloud: ['M7 18h10a4 4 0 0 0 .5-8A6 6 0 0 0 6 9a4.5 4.5 0 0 0 1 9Z'],
    audience: ['M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Z', 'M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6Z'],
    players: ['M8 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z', 'M16 10a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5Z', 'M2 20c.5-4 2.5-6 6-6s5.5 2 6 6', 'M13 15c1-.8 2-.9 3-.9 3 0 5 1.8 6 5.9'],
    clock: ['M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Z', 'M12 7v5l3 2'],
  };

  function makeSvgIcon(kind, className = 'badge-icon') {
    const svg = document.createElementNS(SVG_NS, 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('aria-hidden', 'true');
    svg.classList.add(...className.split(/\s+/).filter(Boolean));
    svg.setAttribute('fill', 'none');
    svg.setAttribute('stroke', 'currentColor');
    svg.setAttribute('stroke-width', '1.8');
    svg.setAttribute('stroke-linecap', 'round');
    svg.setAttribute('stroke-linejoin', 'round');
    (svgPaths[kind] || svgPaths.badge).forEach((d) => {
      const path = document.createElementNS(SVG_NS, 'path');
      path.setAttribute('d', d);
      svg.appendChild(path);
    });
    return svg;
  }

  function makeAssetIcon(asset, className = 'badge-icon badge-icon-asset') {
    const img = document.createElement('img');
    img.className = className;
    img.src = `assets/platforms/${asset}`;
    img.alt = '';
    img.loading = 'lazy';
    img.addEventListener('error', () => img.remove(), { once: true });
    return img;
  }

  function badgeIcon(label) {
    const text = String(label || '').toLowerCase();
    if (/discord|community|rsdw/.test(text)) return makeAssetIcon(platformAssets.discord);
    if (/steam|\bbuild\b|\bcl[-\s]?\d|current|outdated/.test(text)) return makeAssetIcon(platformAssets.steam);
    if (/runeschema|rune schema|\brune\b/.test(text)) return makeSvgIcon('rune');
    if (/ue4ss|ue4|script|code/.test(text)) return makeSvgIcon('code');
    if (/\bpak\b|paks|package/.test(text)) return makeSvgIcon('package');
    if (/verified|sync|operator|official/.test(text)) return makeSvgIcon('verified');
    if (/dedicated|server|host|singleplayer|co-?op/.test(text)) return makeSvgIcon('server');
    if (/hardcore|creative|normal|custom/.test(text)) return makeSvgIcon('game');
    if (/vanilla|modded|handmade|hybrid/.test(text)) return makeSvgIcon('shield');
    return makeSvgIcon('badge');
  }

  function prependIcon(node, icon) {
    if (!node || !icon || node.querySelector(':scope > .badge-icon, :scope > .metric-icon')) return;
    node.prepend(icon);
  }

  function enhanceBadges(card) {
    card.querySelectorAll('.badges .badge').forEach((badge) => prependIcon(badge, badgeIcon(badge.textContent)));
    card.querySelectorAll('.world-back-section').forEach((section) => {
      if (section.querySelector('h4')?.textContent?.trim().toLowerCase() !== 'badges') return;
      section.querySelectorAll('.world-back-list > span').forEach((badge) => {
        badge.classList.add('back-badge');
        prependIcon(badge, badgeIcon(badge.textContent));
      });
    });
  }

  function platformAsset(platform) {
    const key = String(platform || '').toLowerCase();
    if (key.includes('steam')) return platformAssets.steam;
    if (key.includes('windows')) return platformAssets.windows;
    if (key.includes('linux')) return platformAssets.linux;
    if (key.includes('xbox')) return platformAssets.xbox;
    if (key.includes('playstation')) return platformAssets.playstation;
    if (key.includes('nintendo')) return platformAssets.nintendo;
    if (key.includes('epic')) return platformAssets.epic;
    return '';
  }

  function makeMetric(text, icon, className = '') {
    const span = makeEl('span', className, text);
    if (icon) span.prepend(icon);
    return span;
  }

  function enhanceMetrics(card, world) {
    const metrics = card.querySelector('.world-card-front .card-metrics');
    if (!metrics) return;

    const location = world.countryName || world.countryCode || world.region;
    if (location) {
      const locationNode = [...metrics.children].find((node) => node.textContent.trim() === location);
      if (locationNode && /^[A-Z]{2}$/.test(world.countryCode || '')) {
        const flag = document.createElement('img');
        flag.className = 'metric-icon country-flag';
        flag.src = `assets/flags/4x3/${world.countryCode.toLowerCase()}.svg`;
        flag.alt = '';
        flag.loading = 'lazy';
        flag.addEventListener('error', () => flag.remove(), { once: true });
        prependIcon(locationNode, flag);
      }
    }

    if (world.hosting) {
      const node = [...metrics.children].find((entry) => entry.textContent.trim() === world.hosting);
      prependIcon(node, makeSvgIcon('cloud', 'metric-icon'));
    }
    if (world.audience) {
      const node = [...metrics.children].find((entry) => entry.textContent.trim() === world.audience);
      prependIcon(node, makeSvgIcon('audience', 'metric-icon'));
    }

    const playerNode = [...metrics.children].find((entry) => /players$/i.test(entry.textContent.trim()));
    prependIcon(playerNode, makeSvgIcon('players', 'metric-icon'));
    const lastSeenNode = [...metrics.children].find((entry) => /^Last seen /i.test(entry.textContent.trim()));
    prependIcon(lastSeenNode, makeSvgIcon('clock', 'metric-icon'));

    const asset = platformAsset(world.platform);
    if (world.platform && asset) {
      const platformNode = makeMetric(world.platform.toUpperCase(), makeAssetIcon(asset, 'metric-icon platform-metric-icon'), 'world-platform-badge');
      const community = metrics.querySelector('.world-community-badge');
      if (community) metrics.insertBefore(platformNode, community);
      else metrics.appendChild(platformNode);
    }
  }

  createWorldCard = function createIconEnhancedWorldCard(world) {
    const card = baseCreateWorldCard(world);
    enhanceBadges(card);
    enhanceMetrics(card, world);
    return card;
  };

  queueMicrotask(() => {
    try { if (Array.isArray(allWorlds) && allWorlds.length) renderWorlds(); } catch (_) {}
  });
})();
