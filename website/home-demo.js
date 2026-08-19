/* Interactive homepage demo World. Intentionally excluded from live directory/network data. */
(() => {
  const mount = document.querySelector('.main-directory-cta');
  if (!mount || typeof createWorldCard !== 'function' || typeof normalizeWorld !== 'function') return;

  mount.className = 'section-shell home-demo';
  mount.innerHTML = `
    <div class="home-demo-shell reveal visible">
      <div class="home-demo-heading">
        <div class="section-heading">
          <div class="eyebrow">Interactive World showcase</div>
          <h2>See a Dragonwilds Sync World before you join one.</h2>
          <p>This fictional demo uses the same placard renderer as the live directory. Switch channels to flip the card, or change the setup options to preview how a server can present itself.</p>
        </div>
        <div class="demo-live-label">Demo data · not counted in network stats</div>
      </div>
      <div class="home-demo-grid">
        <div class="demo-placard-column">
          <div class="demo-channel-tabs" role="tablist" aria-label="Demo release channel">
            <button class="demo-channel-tab" type="button" role="tab" data-demo-channel="main" aria-selected="true">Main</button>
            <button class="demo-channel-tab experimental" type="button" role="tab" data-demo-channel="experimental" aria-selected="false">Experimental</button>
          </div>
          <p class="demo-channel-help"><strong>Main</strong> is the recommended experience. <strong>Experimental</strong> flips the same placard to preview active-development information.</p>
          <div class="demo-card-host" id="demo-card-host"></div>
          <div class="demo-card-caption"><span>Click the placard to flip it too.</span><strong>Fictional server · interactive preview</strong></div>
        </div>
        <aside class="demo-builder" aria-label="Create a server preview">
          <div class="demo-builder-head"><div><span>CREATE A SERVER</span><h3>Build the placard live.</h3></div><span>PREVIEW</span></div>
          <div class="demo-step"><div class="demo-step-number">1</div><div class="demo-field"><label for="demo-mode">World type</label><select id="demo-mode"><option value="dedicated">Dedicated Server</option><option value="coop">Co-op Host</option><option value="single">Sync World</option></select></div></div>
          <div class="demo-step"><div class="demo-step-number">2</div><div class="demo-field"><label for="demo-region">Region</label><select id="demo-region"><option>US East</option><option>US West</option><option>Europe</option><option>Oceania</option><option>Asia Pacific</option></select></div></div>
          <div class="demo-step"><div class="demo-step-number">3</div><div class="demo-field"><label for="demo-hosting">Hosting</label><select id="demo-hosting"><option>Dedicated</option><option>Community Hosted</option><option>Self Hosted</option></select></div></div>
          <div class="demo-step"><div class="demo-step-number">4</div><div class="demo-field"><span>Features</span><div class="demo-checks"><label class="demo-check"><input id="demo-modded" type="checkbox" checked> Modded</label><label class="demo-check"><input id="demo-community" type="checkbox" checked> Discord</label><label class="demo-check"><input id="demo-public" type="checkbox" checked> Public</label></div></div></div>
          <div class="demo-step"><div class="demo-step-number">5</div><div class="demo-field"><label for="demo-background">Placard background</label><select id="demo-background"><option value="1">Placard 1</option><option value="2">Placard 2</option><option value="3" selected>Placard 3</option><option value="4">Placard 4</option></select></div></div>
          <div class="demo-builder-actions"><a class="button button-primary" href="servers.html">Browse real servers <span aria-hidden="true">→</span></a><button class="demo-reset" id="demo-reset" type="button">Reset</button></div>
        </aside>
      </div>
    </div>`;

  const host = document.querySelector('#demo-card-host');
  const tabs = [...document.querySelectorAll('[data-demo-channel]')];
  const fields = {
    mode: document.querySelector('#demo-mode'),
    region: document.querySelector('#demo-region'),
    hosting: document.querySelector('#demo-hosting'),
    modded: document.querySelector('#demo-modded'),
    community: document.querySelector('#demo-community'),
    public: document.querySelector('#demo-public'),
    background: document.querySelector('#demo-background'),
  };
  let activeChannel = 'main';
  let demoCard = null;

  function rawWorld(channel) {
    const isExperimental = channel === 'experimental';
    const modded = fields.modded.checked;
    const community = fields.community.checked;
    const isPublic = fields.public.checked;
    const mode = fields.mode.value;
    const badges = [
      'Steam', 'Windows', 'Verified',
      ...(community ? ['Discord'] : []),
      ...(modded ? ['Nexus Mods', 'Modded'] : []),
      ...(isExperimental ? ['Experimental'] : ['Current']),
    ];
    return {
      world_id: isExperimental ? 'demo-ashenfall-exp' : 'demo-ashenfall-main',
      nickname: 'Ashenfall',
      world_name: 'Ashenfall Demo World',
      description: isExperimental
        ? 'Development-channel preview with upcoming runtime, WebGUI, synchronization, and placard features before they graduate to Main.'
        : 'A friendly modded dedicated world showcasing synchronized clients, curated mods, public discovery, and secure remote administration.',
      region: fields.region.value,
      country_code: 'US',
      country_name: 'United States',
      version: isExperimental ? 'CL-DEV' : (window.currentSteamServerBuild || 'CL-CURRENT'),
      status: 'online',
      players: { current: isExperimental ? 4 : 12, max: 20 },
      tags: [
        isExperimental ? 'Experimental' : 'Main',
        mode === 'coop' ? 'Co-op' : mode === 'single' ? 'Sync World' : 'Dedicated',
        ...(modded ? ['Modded', 'Curated Mods'] : ['Vanilla']),
        ...(isPublic ? ['Public'] : ['Private']),
      ],
      mods: modded ? ['DragonCore', 'ProximityLoot', 'Extended Resources', 'Better Capes'] : [],
      rules: ['Be respectful', 'No griefing', 'Keep builds server-friendly', 'Have fun'],
      badges,
      placard_background: fields.background.value,
      banner_url: 'assets/demo-world-banner.svg',
      icon_url: 'assets/demo-world-icon.svg',
      source_name: 'Dragonwilds Sync Demo',
      host_type: mode,
      hosting: fields.hosting.value,
      audience: isPublic ? 'Public' : 'Invite Only',
      platform: 'Steam',
      content_type: modded ? 'Modded' : 'Vanilla',
      game_mode: isExperimental ? 'Preview' : 'Adventure',
      community: community ? { name: 'RSDW Community', invite_url: 'https://discord.gg/gQ7uY2cQ3q' } : {},
      rating: { average: isExperimental ? 4.6 : 4.9, count: isExperimental ? 18 : 128 },
      last_seen: Date.now(),
      public_connect: isPublic ? { host: 'demo.dragonwilds.invalid', port: 7777 } : null,
      steam_build_id: window.currentSteamServerBuild || '',
    };
  }

  function buildDualFaceCard() {
    const mainWorld = normalizeWorld(rawWorld('main'));
    const expWorld = normalizeWorld(rawWorld('experimental'));
    const mainCard = createWorldCard(mainWorld);
    const expCard = createWorldCard(expWorld);
    const inner = mainCard.querySelector('.world-card-inner');
    const oldBack = inner?.querySelector('.world-card-back');
    const expFace = expCard.querySelector('.world-card-front');
    if (!inner || !expFace) return mainCard;
    oldBack?.remove();
    expFace.classList.remove('world-card-front');
    expFace.classList.add('world-card-back', 'demo-experimental-face');
    const modeBanner = expFace.querySelector('.world-mode-banner');
    if (modeBanner) modeBanner.textContent = expWorld.modeLabel;
    const hint = expFace.querySelector('.card-flip-hint');
    if (hint) hint.textContent = 'MAIN ↻';
    const experimentalRibbon = document.createElement('div');
    experimentalRibbon.className = 'demo-experimental-ribbon';
    experimentalRibbon.dataset.releaseChannel = 'experimental';
    experimentalRibbon.innerHTML = '<span class="demo-experimental-ribbon-dot" aria-hidden="true"></span><strong>EXPERIMENTAL CHANNEL</strong><span>Active development · May be unstable</span>';
    expFace.appendChild(experimentalRibbon);
    inner.appendChild(expFace);
    mainCard.setAttribute('aria-label', 'Interactive Ashenfall demo World placard. Main and Experimental release channels.');
    mainCard.addEventListener('click', () => queueMicrotask(syncTabsFromCard));
    mainCard.addEventListener('keydown', () => queueMicrotask(syncTabsFromCard));
    return mainCard;
  }

  function syncTabsFromCard() {
    if (!demoCard) return;
    activeChannel = demoCard.classList.contains('flipped') ? 'experimental' : 'main';
    tabs.forEach((tab) => tab.setAttribute('aria-selected', String(tab.dataset.demoChannel === activeChannel)));
  }

  function setChannel(channel) {
    activeChannel = channel === 'experimental' ? 'experimental' : 'main';
    if (demoCard) demoCard.classList.toggle('flipped', activeChannel === 'experimental');
    tabs.forEach((tab) => tab.setAttribute('aria-selected', String(tab.dataset.demoChannel === activeChannel)));
  }

  function renderDemo() {
    host.replaceChildren();
    demoCard = buildDualFaceCard();
    host.appendChild(demoCard);
    setChannel(activeChannel);
  }

  tabs.forEach((tab) => tab.addEventListener('click', () => setChannel(tab.dataset.demoChannel)));
  Object.values(fields).forEach((field) => field.addEventListener('change', renderDemo));
  document.querySelector('#demo-reset')?.addEventListener('click', () => {
    fields.mode.value = 'dedicated';
    fields.region.value = 'US East';
    fields.hosting.value = 'Dedicated';
    fields.modded.checked = true;
    fields.community.checked = true;
    fields.public.checked = true;
    fields.background.value = '3';
    activeChannel = 'main';
    renderDemo();
  });

  renderDemo();
})();
