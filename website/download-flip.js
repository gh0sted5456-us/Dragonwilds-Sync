/* Release-channel download flip card. */
(() => {
  const downloads = document.querySelector('#downloads');
  const oldPanel = downloads?.querySelector('.download-panel');
  if (!downloads || !oldPanel) return;

  const EXP_BRANCH = 'codex/webgui-catalog-console-overhaul';
  const EXP_API = `https://api.github.com/repos/gh0sted5456-us/Dragonwilds-Sync/branches/${encodeURIComponent(EXP_BRANCH)}`;
  const EXP_ZIP = `https://github.com/gh0sted5456-us/Dragonwilds-Sync/archive/refs/heads/${EXP_BRANCH}.zip`;
  const EXP_PAGE = `https://github.com/gh0sted5456-us/Dragonwilds-Sync/tree/${EXP_BRANCH}`;

  const flip = document.createElement('div');
  flip.className = 'download-flip reveal visible';
  flip.dataset.releaseSurface = 'true';
  flip.innerHTML = `
    <div class="download-flip-inner">
      <section class="download-face main" aria-label="Main release download">
        <div class="download-face-main">
          <div class="eyebrow">Main · Primary release channel</div>
          <h2>Ready when your world is.</h2>
          <p>Grab the newest published Dragonwilds Sync Main release from GitHub. Main is the recommended channel for normal use.</p>
          <div class="download-meta"><div><span>VERSION</span><strong data-main-version>Checking…</strong></div><div><span>PUBLISHED</span><strong data-main-date>GitHub Releases</strong></div><div><span>CHANNEL</span><strong>Main</strong></div></div>
          <p>Dragonwilds Sync is a passion project. Donations help with hosting, tools, and development costs, but features will never be locked behind a paywall.</p>
        </div>
        <div class="download-face-side">
          <div class="download-platform-icons" aria-label="Supported platform"><img src="assets/platforms/windows.svg" alt="Windows"><img src="assets/platforms/steam.svg" alt="Steam"></div>
          <img src="assets/application-icon.png" alt="Dragonwilds Sync icon">
          <a class="button button-primary button-full" data-main-download href="https://github.com/gh0sted5456-us/Dragonwilds-Sync/releases">Download Main <span aria-hidden="true">↗</span></a>
          <a class="text-link" href="https://github.com/gh0sted5456-us/Dragonwilds-Sync/releases">Main release history</a>
        </div>
        <button class="channel-ribbon" type="button" data-channel-flip="experimental" data-release-channel="experimental" aria-label="Show Experimental download channel"><span class="ribbon-dot"></span>Experimental Channel <span aria-hidden="true">↻</span></button>
      </section>
      <section class="download-face experimental" aria-label="Experimental release download">
        <div class="download-face-main">
          <span class="download-channel-pill">Experimental · Active development</span>
          <h2>Preview what comes next.</h2>
          <p>The Experimental channel tracks active development before changes graduate to Main. It may be unstable and should be used by testers who are comfortable reporting issues.</p>
          <div class="download-meta"><div><span>BRANCH</span><strong>${EXP_BRANCH}</strong></div><div><span>LATEST COMMIT</span><strong data-exp-sha>Checking…</strong></div><div><span>UPDATED</span><strong data-exp-date>Checking…</strong></div></div>
          <p>Experimental builds can change quickly. Back up important server configuration before testing development-channel builds.</p>
        </div>
        <div class="download-face-side">
          <div class="download-platform-icons" aria-label="Experimental platform"><img src="assets/platforms/windows.svg" alt="Windows"><img src="assets/platforms/steam.svg" alt="Steam"><img src="assets/platforms/github.svg" alt="GitHub" onerror="this.remove()"></div>
          <img src="assets/application-icon.png" alt="Dragonwilds Sync icon">
          <a class="button button-primary button-full" href="${EXP_ZIP}">Download Experimental ZIP <span aria-hidden="true">↓</span></a>
          <a class="text-link" href="${EXP_PAGE}" target="_blank" rel="noopener noreferrer">View Experimental branch ↗</a>
        </div>
        <button class="channel-ribbon" type="button" data-channel-flip="main" data-release-channel="main" aria-label="Return to Main download channel"><span class="ribbon-dot"></span>Main Channel <span aria-hidden="true">↻</span></button>
      </section>
    </div>`;

  oldPanel.replaceWith(flip);

  const legacyChannels = [...downloads.querySelectorAll('.release-channels .release-channel')];
  const legacyMain = legacyChannels.find((node) => /\bmain\b/i.test(node.textContent || ''));
  const legacyExperimental = legacyChannels.find((node) => /experimental/i.test(node.textContent || ''));

  // Convert the original release cards into in-page controls instead of outbound links.
  if (legacyMain) {
    legacyMain.removeAttribute('href');
    legacyMain.removeAttribute('target');
    legacyMain.removeAttribute('rel');
    legacyMain.setAttribute('role', 'button');
    legacyMain.setAttribute('tabindex', '0');
    legacyMain.dataset.channelFlip = 'main';
  }
  if (legacyExperimental) {
    legacyExperimental.removeAttribute('href');
    legacyExperimental.removeAttribute('target');
    legacyExperimental.removeAttribute('rel');
    legacyExperimental.setAttribute('role', 'button');
    legacyExperimental.setAttribute('tabindex', '0');
    legacyExperimental.dataset.channelFlip = 'experimental';
    const arrow = legacyExperimental.querySelector('.release-channel-arrow');
    if (arrow) arrow.textContent = '↻';
  }

  const syncLegacyControls = (side) => {
    [legacyMain, legacyExperimental].forEach((node) => {
      if (!node) return;
      const selected = node.dataset.channelFlip === side;
      node.classList.toggle('active', selected);
      node.setAttribute('aria-pressed', String(selected));
      if (selected) node.setAttribute('aria-current', 'true');
      else node.removeAttribute('aria-current');
    });
  };

  const setSide = (side) => {
    const next = side === 'experimental' ? 'experimental' : 'main';
    flip.classList.toggle('flipped', next === 'experimental');
    flip.dataset.activeReleaseChannel = next;
    syncLegacyControls(next);
  };

  flip.querySelectorAll('[data-channel-flip]').forEach((button) => button.addEventListener('click', () => setSide(button.dataset.channelFlip)));
  [legacyMain, legacyExperimental].forEach((control) => {
    if (!control) return;
    control.addEventListener('click', (event) => {
      event.preventDefault();
      setSide(control.dataset.channelFlip);
    });
    control.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        setSide(control.dataset.channelFlip);
      }
    });
  });

  // Mirror the existing Main release loader without depending on its old DOM nodes.
  fetch('https://api.github.com/repos/gh0sted5456-us/Dragonwilds-Sync/releases/latest', { headers: { Accept: 'application/vnd.github+json' } })
    .then((response) => { if (!response.ok) throw new Error('release lookup failed'); return response.json(); })
    .then((release) => {
      const date = new Date(release.published_at || release.created_at);
      const version = release.tag_name || release.name || 'Latest';
      flip.querySelector('[data-main-version]').textContent = version;
      flip.querySelector('[data-main-date]').textContent = Number.isNaN(date.getTime()) ? 'GitHub Releases' : date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
      if (release.html_url) flip.querySelector('[data-main-download]').href = release.html_url;
    }).catch(() => {
      flip.querySelector('[data-main-version]').textContent = 'Latest available';
      flip.querySelector('[data-main-date]').textContent = 'GitHub Releases';
    });

  fetch(EXP_API, { headers: { Accept: 'application/vnd.github+json' } })
    .then((response) => { if (!response.ok) throw new Error('branch lookup failed'); return response.json(); })
    .then((branch) => {
      const sha = String(branch?.commit?.sha || '').slice(0, 8);
      const dateRaw = branch?.commit?.commit?.committer?.date || branch?.commit?.commit?.author?.date;
      const date = dateRaw ? new Date(dateRaw) : null;
      flip.querySelector('[data-exp-sha]').textContent = sha || 'Development';
      flip.querySelector('[data-exp-date]').textContent = date && !Number.isNaN(date.getTime()) ? date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' }) : 'Active development';
    }).catch(() => {
      flip.querySelector('[data-exp-sha]').textContent = 'Development';
      flip.querySelector('[data-exp-date]').textContent = 'Active development';
    });

  setSide('main');
})();
