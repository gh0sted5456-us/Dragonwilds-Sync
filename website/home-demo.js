/* Interactive homepage demo World. Intentionally excluded from live directory/network data. */
(() => {
  const mount = document.querySelector('.main-directory-cta');
  if (!mount || typeof createWorldCard !== 'function' || typeof normalizeWorld !== 'function') return;

  const REGION_MAP = Object.freeze({
    'US East': { code: 'US', name: 'United States' },
    'US West': { code: 'US', name: 'United States' },
    'Canada': { code: 'CA', name: 'Canada' },
    'Europe': { code: 'DE', name: 'Germany' },
    'Oceania': { code: 'AU', name: 'Australia' },
    'Asia Pacific': { code: 'JP', name: 'Japan' },
  });

  const PLATFORM_OPTIONS = [
    ['steam', 'Steam', 'assets/platforms/steam.svg'],
    ['windows', 'Windows', 'assets/platforms/windows.svg'],
    ['xbox', 'Xbox', 'assets/platforms/xbox.svg'],
    ['playstation', 'PlayStation', 'assets/platforms/playstation.svg'],
    ['nintendo', 'Nintendo', 'assets/platforms/nintendo.svg'],
    ['epicgames', 'Epic Games', 'assets/platforms/epicgames.svg'],
  ];

  const REVIEWS = Object.freeze({
    main: [
      { score: 5, name: 'MapleKnight', text: 'Smooth sync, friendly people, and the curated mod list is easy to understand.' },
      { score: 5, name: 'RuneSmith', text: 'Joined from a fresh profile and everything matched the host without any fuss.' },
      { score: 4, name: 'FellhollowFox', text: 'Great community rules and uptime. Would happily play here again.' },
      { score: 5, name: 'AshRunner', text: 'The placard told me exactly what I needed before joining. Nice server.' },
    ],
    experimental: [
      { score: 5, name: 'TestPilot', text: 'The development features are genuinely useful and the server stayed stable for our session.' },
      { score: 4, name: 'PatchNotes', text: 'A couple rough edges, but the experimental WebGUI changes are promising.' },
      { score: 5, name: 'DragonTester', text: 'Fast sync and a surprisingly smooth preview build.' },
      { score: 4, name: 'BranchWalker', text: 'Good place to test upcoming features before they reach Main.' },
    ],
  });

  mount.className = 'section-shell home-demo';
  mount.innerHTML = `
    <div class="home-demo-shell reveal visible">
      <div class="home-demo-heading">
        <div class="section-heading">
          <div class="eyebrow">Interactive World showcase</div>
          <h2>Build a World placard, then explore it.</h2>
          <p>Main and Experimental change the World identity. Clicking the placard itself always flips between that channel's front and public-details side.</p>
        </div>
        <div class="demo-live-label">Demo data · never counted in network stats</div>
      </div>
      <div class="home-demo-grid">
        <div class="demo-placard-column">
          <div class="demo-card-toolbar">
            <div class="demo-channel-tabs" role="tablist" aria-label="Demo release channel">
              <button class="demo-channel-tab" type="button" role="tab" data-demo-channel="main" aria-selected="true">Main</button>
              <button class="demo-channel-tab experimental" type="button" role="tab" data-demo-channel="experimental" aria-selected="false">Experimental</button>
            </div>
            <div class="demo-layout-tabs" role="group" aria-label="Placard layout">
              <button class="demo-layout-tab" type="button" data-demo-layout="standard" aria-pressed="true">Standard</button>
              <button class="demo-layout-tab" type="button" data-demo-layout="horizontal" aria-pressed="false">Horizontal</button>
            </div>
          </div>
          <p class="demo-channel-help"><strong>Channel changes identity.</strong> Click the placard for its description, community rules, mods, badges, and tags. Click the stars to open demo reviews.</p>
          <div class="demo-card-host" id="demo-card-host"></div>
          <div class="demo-card-caption"><span>Placard click = front/details.</span><strong>Fictional server · interactive preview</strong></div>
        </div>
        <aside class="demo-builder" aria-label="Create a server preview">
          <div class="demo-builder-head"><div><span>CREATE A SERVER</span><h3>Fully editable placard preview</h3></div><span>LOCAL PREVIEW</span></div>

          <div class="demo-step">
            <div class="demo-step-number">1</div>
            <div class="demo-field demo-field-stack">
              <label for="demo-name">World identity</label>
              <input id="demo-name" type="text" maxlength="90" value="Ashenfall" aria-label="World name">
              <textarea id="demo-description" rows="3" maxlength="360" aria-label="World description">A friendly modded dedicated world showcasing synchronized clients, curated mods, public discovery, and secure remote administration.</textarea>
            </div>
          </div>

          <div class="demo-step">
            <div class="demo-step-number">2</div>
            <div class="demo-field demo-field-grid">
              <label>World configuration</label>
              <div class="demo-inline-fields">
                <select id="demo-mode" aria-label="World type"><option value="dedicated">Dedicated Server</option><option value="coop">Co-op Host</option><option value="single">Sync World</option></select>
                <select id="demo-hosting" aria-label="Hosting"><option>Dedicated</option><option>Community Hosted</option><option>Self Hosted</option></select>
              </div>
              <div class="demo-region-row">
                <select id="demo-region" aria-label="Region"><option>US East</option><option>US West</option><option>Canada</option><option>Europe</option><option>Oceania</option><option>Asia Pacific</option></select>
                <span class="demo-region-preview"><img id="demo-region-flag" alt=""><b id="demo-region-country">United States</b></span>
              </div>
            </div>
          </div>

          <div class="demo-step">
            <div class="demo-step-number">3</div>
            <div class="demo-field">
              <span>Platforms</span>
              <div class="demo-platforms">
                ${PLATFORM_OPTIONS.map(([key, label, src], index) => `<label class="demo-platform"><input type="checkbox" data-demo-platform="${key}" data-label="${label}" ${index < 2 ? 'checked' : ''}><img src="${src}" alt=""><span>${label}</span></label>`).join('')}
              </div>
            </div>
          </div>

          <div class="demo-step">
            <div class="demo-step-number">4</div>
            <div class="demo-field demo-field-stack">
              <span>Features & public content</span>
              <div class="demo-checks">
                <label class="demo-check"><input id="demo-modded" type="checkbox" checked> Modded</label>
                <label class="demo-check"><input id="demo-community" type="checkbox" checked> Discord</label>
                <label class="demo-check"><input id="demo-public" type="checkbox" checked> Public</label>
              </div>
              <input id="demo-tags" type="text" value="Curated Mods, Friendly, Building" aria-label="Comma separated tags" placeholder="Tags, comma separated">
              <input id="demo-mods" type="text" value="DragonCore, ProximityLoot, Extended Resources, Better Capes" aria-label="Comma separated mods" placeholder="Mods, comma separated">
              <textarea id="demo-rules" rows="3" aria-label="Community rules" placeholder="One community rule per line">Be respectful
No griefing
Keep builds server-friendly
Have fun</textarea>
            </div>
          </div>

          <div class="demo-step">
            <div class="demo-step-number">5</div>
            <div class="demo-field demo-field-stack">
              <label for="demo-background">Appearance</label>
              <select id="demo-background"><option value="1">Placard 1</option><option value="2">Placard 2</option><option value="3" selected>Placard 3</option><option value="4">Placard 4</option></select>
              <div class="demo-upload-grid">
                <label class="demo-upload"><strong>Icon image</strong><span id="demo-icon-label">Use demo icon</span><input id="demo-icon-file" type="file" accept="image/png,image/jpeg,image/webp,image/gif"></label>
                <label class="demo-upload"><strong>Banner image</strong><span id="demo-banner-label">Use demo banner</span><input id="demo-banner-file" type="file" accept="image/png,image/jpeg,image/webp,image/gif"></label>
              </div>
              <small class="demo-local-note">Image files stay in this browser tab for preview only. They are not uploaded.</small>
            </div>
          </div>

          <div class="demo-builder-actions"><a class="button button-primary" href="servers.html">Browse real servers <span aria-hidden="true">→</span></a><button class="demo-reset" id="demo-reset" type="button">Reset preview</button></div>
        </aside>
      </div>
    </div>`;

  const host = document.querySelector('#demo-card-host');
  const shell = mount.querySelector('.home-demo-shell');
  const channelTabs = [...mount.querySelectorAll('[data-demo-channel]')];
  const layoutTabs = [...mount.querySelectorAll('[data-demo-layout]')];
  const platformInputs = [...mount.querySelectorAll('[data-demo-platform]')];
  const fields = {
    name: mount.querySelector('#demo-name'),
    description: mount.querySelector('#demo-description'),
    mode: mount.querySelector('#demo-mode'),
    region: mount.querySelector('#demo-region'),
    hosting: mount.querySelector('#demo-hosting'),
    modded: mount.querySelector('#demo-modded'),
    community: mount.querySelector('#demo-community'),
    public: mount.querySelector('#demo-public'),
    tags: mount.querySelector('#demo-tags'),
    mods: mount.querySelector('#demo-mods'),
    rules: mount.querySelector('#demo-rules'),
    background: mount.querySelector('#demo-background'),
    iconFile: mount.querySelector('#demo-icon-file'),
    bannerFile: mount.querySelector('#demo-banner-file'),
  };

  let activeChannel = 'main';
  let activeLayout = 'standard';
  let demoCard = null;
  let localIconUrl = '';
  let localBannerUrl = '';

  const csv = (value, max = 8) => String(value || '').split(',').map((item) => item.trim()).filter(Boolean).slice(0, max);
  const lines = (value, max = 8) => String(value || '').split(/\r?\n/).map((item) => item.trim()).filter(Boolean).slice(0, max);
  const regionData = () => REGION_MAP[fields.region.value] || REGION_MAP['US East'];
  const selectedPlatforms = () => platformInputs.filter((input) => input.checked).map((input) => ({ key: input.dataset.demoPlatform, label: input.dataset.label }));

  function updateRegionPreview() {
    const region = regionData();
    const flag = mount.querySelector('#demo-region-flag');
    const label = mount.querySelector('#demo-region-country');
    if (flag) {
      flag.src = `assets/flags/4x3/${region.code.toLowerCase()}.svg`;
      flag.alt = `${region.name} flag`;
    }
    if (label) label.textContent = region.name;
  }

  function rawWorld(channel) {
    const isExperimental = channel === 'experimental';
    const modded = fields.modded.checked;
    const community = fields.community.checked;
    const isPublic = fields.public.checked;
    const mode = fields.mode.value;
    const region = regionData();
    const platforms = selectedPlatforms();
    const name = fields.name.value.trim() || 'Ashenfall';
    const description = fields.description.value.trim() || 'A Dragonwilds Sync demo World.';
    const customTags = csv(fields.tags.value, 6);
    const mods = modded ? csv(fields.mods.value, 8) : [];
    const rules = lines(fields.rules.value, 8);
    const platformLabels = platforms.map((entry) => entry.label);
    const badges = [
      ...platformLabels,
      'Verified',
      ...(community ? ['Discord'] : []),
      ...(modded ? ['Nexus Mods', 'Modded'] : []),
      ...(isExperimental ? ['Experimental'] : ['Current']),
    ];

    return {
      world_id: `demo-${name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'world'}-${channel}`,
      nickname: name,
      world_name: `${name} Demo World`,
      description,
      region: fields.region.value,
      country_code: region.code,
      country_name: region.name,
      version: isExperimental ? 'CL-DEV' : (window.currentSteamServerBuild || 'CL-CURRENT'),
      status: 'online',
      players: { current: isExperimental ? 4 : 12, max: 20 },
      tags: [
        isExperimental ? 'Experimental' : 'Main',
        mode === 'coop' ? 'Co-op' : mode === 'single' ? 'Sync World' : 'Dedicated',
        ...(modded ? ['Modded'] : ['Vanilla']),
        ...(isPublic ? ['Public'] : ['Private']),
        ...customTags,
      ].slice(0, 8),
      mods,
      rules,
      badges,
      placard_background: fields.background.value,
      banner_url: localBannerUrl || 'assets/demo-world-banner.svg',
      icon_url: localIconUrl || 'assets/demo-world-icon.svg',
      source_name: 'Dragonwilds Sync Demo',
      host_type: mode,
      hosting: fields.hosting.value,
      audience: isPublic ? 'Public' : 'Invite Only',
      platform: platforms[0]?.label || '',
      content_type: modded ? 'Modded' : 'Vanilla',
      game_mode: isExperimental ? 'Preview' : 'Adventure',
      community: community ? { name: 'RSDW Community', invite_url: 'https://discord.gg/gQ7uY2cQ3q' } : {},
      rating: { average: isExperimental ? 4.6 : 4.9, count: isExperimental ? 18 : 128 },
      last_seen: Date.now(),
      public_connect: isPublic ? { host: 'demo.dragonwilds.invalid', port: 7777 } : null,
      steam_build_id: window.currentSteamServerBuild || '',
      release_channel: channel,
    };
  }

  function addExperimentalRibbon(card) {
    if (activeChannel !== 'experimental') return;
    card.classList.add('demo-experimental-card');
    card.querySelectorAll('.world-card-face').forEach((face) => {
      const ribbon = document.createElement('div');
      ribbon.className = 'demo-experimental-ribbon';
      ribbon.dataset.releaseChannel = 'experimental';
      ribbon.innerHTML = '<span class="demo-experimental-ribbon-dot" aria-hidden="true"></span><strong>EXPERIMENTAL CHANNEL</strong><span>Active development · May be unstable</span>';
      face.appendChild(ribbon);
    });
  }

  function ensureReviewsDialog() {
    let dialog = document.querySelector('#demo-reviews-dialog');
    if (dialog) return dialog;
    dialog = document.createElement('dialog');
    dialog.id = 'demo-reviews-dialog';
    dialog.className = 'demo-reviews-dialog';
    dialog.innerHTML = '<div class="demo-reviews-window"><div class="demo-reviews-head"><div><span>DEMO REVIEWS</span><h3></h3></div><button type="button" class="demo-review-close" aria-label="Close reviews">×</button></div><div class="demo-reviews-summary"></div><div class="demo-review-list"></div><p class="demo-review-note">Fictional review data for the interactive website preview.</p></div>';
    document.body.appendChild(dialog);
    dialog.querySelector('.demo-review-close').addEventListener('click', () => dialog.close());
    dialog.addEventListener('click', (event) => { if (event.target === dialog) dialog.close(); });
    return dialog;
  }

  function openReviews(world) {
    const dialog = ensureReviewsDialog();
    const reviews = REVIEWS[activeChannel];
    dialog.querySelector('h3').textContent = `${world.name} reviews`;
    dialog.querySelector('.demo-reviews-summary').innerHTML = `<strong>${world.ratingAverage.toFixed(1)}</strong><span>${'★'.repeat(Math.round(world.ratingAverage))}${'☆'.repeat(5 - Math.round(world.ratingAverage))}</span><small>${world.ratingCount} ratings</small>`;
    const list = dialog.querySelector('.demo-review-list');
    list.replaceChildren();
    reviews.forEach((review) => {
      const row = document.createElement('article');
      row.className = 'demo-review-row';
      row.innerHTML = `<div><strong>${review.name}</strong><span>${'★'.repeat(review.score)}${'☆'.repeat(5 - review.score)}</span></div><p>${review.text}</p>`;
      list.appendChild(row);
    });
    if (typeof dialog.showModal === 'function') dialog.showModal();
    else dialog.setAttribute('open', '');
  }

  function enhanceRating(card, world) {
    const rating = card.querySelector('.world-card-front .world-rating');
    if (!rating) return;
    rating.classList.add('demo-rating-button');
    rating.tabIndex = 0;
    rating.setAttribute('role', 'button');
    rating.setAttribute('aria-label', `Open ${world.name} reviews`);
    rating.title = 'View demo reviews';
    rating.addEventListener('click', (event) => {
      event.preventDefault();
      event.stopPropagation();
      openReviews(world);
    });
    rating.addEventListener('keydown', (event) => {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      event.preventDefault();
      event.stopPropagation();
      openReviews(world);
    });
  }

  function buildCard(preserveFlipped = false) {
    const wasFlipped = Boolean(preserveFlipped && demoCard?.classList.contains('flipped'));
    const world = normalizeWorld(rawWorld(activeChannel));
    const card = createWorldCard(world);
    card.classList.toggle('demo-horizontal-card', activeLayout === 'horizontal');
    addExperimentalRibbon(card);
    enhanceRating(card, world);
    if (wasFlipped) {
      card.classList.add('flipped');
      card.setAttribute('aria-pressed', 'true');
    }
    card.setAttribute('aria-label', `${world.name} demo placard. ${activeChannel === 'experimental' ? 'Experimental' : 'Main'} channel. Click to flip between front and details.`);
    return card;
  }

  function renderDemo({ preserveSide = true } = {}) {
    const wasFlipped = Boolean(preserveSide && demoCard?.classList.contains('flipped'));
    host.replaceChildren();
    demoCard = buildCard(false);
    if (wasFlipped) {
      demoCard.classList.add('flipped');
      demoCard.setAttribute('aria-pressed', 'true');
    }
    host.appendChild(demoCard);
    host.classList.toggle('horizontal', activeLayout === 'horizontal');
    shell.classList.toggle('demo-horizontal-layout', activeLayout === 'horizontal');
    updateRegionPreview();
  }

  function setChannel(channel) {
    activeChannel = channel === 'experimental' ? 'experimental' : 'main';
    channelTabs.forEach((tab) => tab.setAttribute('aria-selected', String(tab.dataset.demoChannel === activeChannel)));
    renderDemo({ preserveSide: false });
  }

  function setLayout(layout) {
    activeLayout = layout === 'horizontal' ? 'horizontal' : 'standard';
    layoutTabs.forEach((tab) => tab.setAttribute('aria-pressed', String(tab.dataset.demoLayout === activeLayout)));
    renderDemo({ preserveSide: true });
  }

  function loadLocalImage(file, kind) {
    if (!file) return;
    const okay = /^image\/(?:png|jpe?g|webp|gif)$/i.test(file.type);
    if (!okay || file.size > 6 * 1024 * 1024) {
      window.alert('Use a PNG, JPEG, WebP, or GIF image up to 6 MB for this local preview.');
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      if (kind === 'icon') {
        localIconUrl = String(reader.result || '');
        mount.querySelector('#demo-icon-label').textContent = file.name;
      } else {
        localBannerUrl = String(reader.result || '');
        mount.querySelector('#demo-banner-label').textContent = file.name;
      }
      renderDemo({ preserveSide: true });
    };
    reader.readAsDataURL(file);
  }

  channelTabs.forEach((tab) => tab.addEventListener('click', () => setChannel(tab.dataset.demoChannel)));
  layoutTabs.forEach((tab) => tab.addEventListener('click', () => setLayout(tab.dataset.demoLayout)));

  [fields.name, fields.description, fields.tags, fields.mods, fields.rules].forEach((field) => field.addEventListener('input', () => renderDemo({ preserveSide: true })));
  [fields.mode, fields.region, fields.hosting, fields.modded, fields.community, fields.public, fields.background].forEach((field) => field.addEventListener('change', () => renderDemo({ preserveSide: true })));
  platformInputs.forEach((field) => field.addEventListener('change', () => renderDemo({ preserveSide: true })));
  fields.iconFile.addEventListener('change', () => loadLocalImage(fields.iconFile.files?.[0], 'icon'));
  fields.bannerFile.addEventListener('change', () => loadLocalImage(fields.bannerFile.files?.[0], 'banner'));

  mount.querySelector('#demo-reset')?.addEventListener('click', () => {
    fields.name.value = 'Ashenfall';
    fields.description.value = 'A friendly modded dedicated world showcasing synchronized clients, curated mods, public discovery, and secure remote administration.';
    fields.mode.value = 'dedicated';
    fields.region.value = 'US East';
    fields.hosting.value = 'Dedicated';
    fields.modded.checked = true;
    fields.community.checked = true;
    fields.public.checked = true;
    fields.tags.value = 'Curated Mods, Friendly, Building';
    fields.mods.value = 'DragonCore, ProximityLoot, Extended Resources, Better Capes';
    fields.rules.value = 'Be respectful\nNo griefing\nKeep builds server-friendly\nHave fun';
    fields.background.value = '3';
    fields.iconFile.value = '';
    fields.bannerFile.value = '';
    mount.querySelector('#demo-icon-label').textContent = 'Use demo icon';
    mount.querySelector('#demo-banner-label').textContent = 'Use demo banner';
    platformInputs.forEach((input, index) => { input.checked = index < 2; });
    localIconUrl = '';
    localBannerUrl = '';
    activeChannel = 'main';
    activeLayout = 'standard';
    channelTabs.forEach((tab) => tab.setAttribute('aria-selected', String(tab.dataset.demoChannel === 'main')));
    layoutTabs.forEach((tab) => tab.setAttribute('aria-pressed', String(tab.dataset.demoLayout === 'standard')));
    renderDemo({ preserveSide: false });
  });

  ensureReviewsDialog();
  updateRegionPreview();
  renderDemo({ preserveSide: false });
})();
