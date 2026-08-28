(() => {
  const root = document.getElementById('app');
  const modalRoot = document.getElementById('modal-root');
  const toastRoot = document.getElementById('toast-root');
  const internalTaskbar = document.getElementById('internal-taskbar');
  let taskbarDisplayMode = (()=>{ try { return localStorage.getItem('dragonwilds-sync-taskbar-mode') === 'icons' ? 'icons' : 'tabs'; } catch (_) { return 'tabs'; } })();
  let desktopWindowSeq = 0;
  // Popup windows must remain above placards (Phase 4/5 use the 10020-10100
  // range). Starting below them made a visible mod/review window receive clicks
  // through the higher placard surface.
  let desktopZ = 11000;
  const query = new URLSearchParams(window.location.search);
  const detachedMode = query.get('detached') === '1';
  // UE4SS ships these Lua mods baked into its own default distribution (loader/console/cheat
  // scaffolding, not something the player installed). They physically exist on disk and stay
  // untouched, but they aren't presented in the load-order list since there's nothing for a
  // player or server operator to manage about them.
  const UE4SS_BAKED_IN_MOD_NAMES = new Set(['bpml_genericfunctions','bpmodloadermod','cheatmanagerenablermod','consolecommandsmod','consoleenablermod','keybinds','shared']);
  const isBakedInUe4ssMod = (unit) => unit && unit.group === 'ue4ss_mod' && UE4SS_BAKED_IN_MOD_NAMES.has(String(unit.name || '').trim().toLowerCase());
  const detachedRoute = query.get('route') || '';
  let detachedContext = {};
  try { detachedContext = query.get('ctx') ? JSON.parse(atob(query.get('ctx').replace(/-/g,'+').replace(/_/g,'/'))) : {}; } catch (_) { detachedContext = {}; }
  const uiSwapMetrics=[];let pendingUiSwap=null;const MAX_UI_SWAP_METRICS=160;
  let detachedCloseGuard=null;
  const percentile=(values,p)=>{if(!values.length)return 0;const sorted=[...values].sort((a,b)=>a-b);return sorted[Math.min(sorted.length-1,Math.max(0,Math.ceil(sorted.length*p)-1))];};
  function uiSwapSnapshot(){
    const rows=uiSwapMetrics.slice();const sync=rows.map((row)=>row.sync_ms),settled=rows.map((row)=>row.settled_ms);
    return {count:rows.length,sync_p50_ms:percentile(sync,.5),sync_p95_ms:percentile(sync,.95),settled_p50_ms:percentile(settled,.5),settled_p95_ms:percentile(settled,.95),budget:{sync_ms:50,settled_ms:120},rows};
  }
  window.__DWSYNC_SWAP_METRICS__={snapshot:uiSwapSnapshot,clear:()=>{uiSwapMetrics.length=0;pendingUiSwap=null;}};
  document.addEventListener('click',(event)=>{
    const target=event.target?.closest?.('button,[data-route],[role="tab"]');if(!target)return;
    const entry=Object.entries(target.dataset||{}).find(([key])=>/(route|appy|tab|section|tool|view)$/i.test(key));
    if(!entry)return;
    pendingUiSwap={kind:entry[0],target:String(entry[1]||target.textContent||'').trim().slice(0,100),startedAt:performance.now(),wallAt:Date.now()};
  },true);

  const state = {
    data: null,
    route: 'worlds',
    selectedWorldId: null,
    selectedServerWorldId: null,
    serverTab: 'overview',
    privateTab: 'overview',
    privateWorldView: 'cards',
    serverWorldView: 'cards',
    worldManagementTab: 'worlds',
    worldManagementView: 'cards',
    worldManagementPage: 1,
    serversTab: 'worlds',
    privateWorldPage: 1,
    serverWorldPage: 1,
    privateProfileDetails: {},
    singleplayerConfigs: {},
    navigationHistory: [],
    mapCacheStatus: null,
    mapOverlays: null,
    mapOverlayFilters: new Set(['Locations']),
    mapViewports: {},
    vpnCatalog: null,
    serverInventory: {},
    serverBackups: {},
    serverFeedback: {},
    serverFeedbackDays: 30,
    serverFeedbackPage: 1,
    serverConfigs: {},
    serverConsole: {},
    serverTabLoadedAt: {},
    serverTabLoading: {},
    privateTabLoadedAt: {},
    privateTabLoading: {},
    serverSaveStatus: {},
    worldSaveEditors: {},
    serverStarterCharacters: {},
    serverCharacterSubmissions: {},
    singleplayerInventory: [],
    privateInventory: {},
    clientPublicIp: '',
    clientModFilter: 'required',
    settingsTab: 'application',
    webhostTab: 'settings',
    webhostPreviewMode: 'desktop',
    webhostPreviewLoaded: false,
    serverManagementAddress: '',
    serverManagementLoginUrl: '',
    operation: null,
    applicationSettingsTab: 'application',
    helpCategory: 'getting-started',
    helpSearch: '',
    profileTab: 'user',
    nexusStatus: null,
    nexusMod: null,
    nexusFiles: [],
    recommendationMedia: {},
    recommendationMediaBusy: false,
    nexusTarget: null,
    nexusPending: null,
    modRepository: null,
    modRepositoryLoading: false,
    modRepositoryError: '',
    modRepositorySearch: '',
    nexusAutoCheckAt: {},
    showNexusIntegration: false,
    integrationStatus: null,
    integrationsLoading: false,
    detachedWindows: [],
    busy: new Set(),
    adminStatus: { platform:'', elevated:false, canRelaunch:false, linux:false, wineProton:false, showLinuxSettings:false },
    discordStatus: null,
    entered: false,
    scrollPositions: {},
    panelStates: {},
    lastScrollKey: '',
    characters: [],
    discordPresenceKey: '',
    discordPresenceStartedAt: 0,
    setupWizardOpen: false,
    setupValidation: null,
    selectedPlayerId: '',
    playerPollTimer: null,
    serverPlayers: {},
    serverPlayerHistoryPage: {},
    serverActivityPage: 1,
    serverAccessConnections: [],
    serverAccessConnectionsLoadedAt: 0,
    serverSpawner: {},
    serverMapConfig: {},
    characterSelectedId: '',
    characterTab: 'skills',
    characterProfileTab: 'overview',
    characterInventoryTab: 'inventory',
    setupMode: 'player',
    sharedWorldsTab: 'packages',
    sharedPackageHistoryPage: 1,
    applicationUpdate: null,
    applicationUpdateResult: null,
    hostingFocusDismissedProfileId: '',
    applicationUpdateMode: null,
    backgroundRefreshTimer: null,
    backgroundRefreshBusy: false,
    backgroundRefreshAt: { worlds:0, runtime:0, directory:0, minimal:0 },
    rsdwSection: 'character',
    rsdwlToolLoading: '',
    rsdwTool: 'character-editor',
    rsdwMapWorldId: '',
    rsdwWorlds: [],
    rsdwCharacterPayload: null,
    rsdwNativeDraft: null,
    rsdwNativeTools: {},
    rsdwCharacterCache: {},
    rsdwNativeToolBusy: '',
    rsdwNativeToolProgress: 0,
    rsdwToolSearch: '',
    rsdwToolPage: 0,
    rsdwItemCatalogTab: 'bag',
    customItemPage: 0,
    rsdwItemBagCategory: '',
    rsdwRecipeCategory: 'all',
    rsdwSpellWheel: [],
    rsdwSpellPage: 0,
    rsdwStudioTab: 'identity',
    rsdwEquipmentRepositorySlot: '',
    rsdwEquipmentSearch: '',
    rsdwPreviewHidden: new Set(),
    rsdwInventorySection: 'inventory',
    rsdwItemRepositoryOpen: true,
    rsdwPreviewWeaponItems: {},
    rsdwCharacterEditorTab: 'appearance',
    rsdwCharacterHistory: [],
    rsdwCharacterFuture: [],
    rsdwCharacterLastChanges: null,
    rsdwAvatarScale: 62,
    rsdwAvatarBackground: 'studio',
    rsdwPreviewPending: false,
    rsdwPreviewAvatar: null,
    rsdwPendingAvatar: null,
    rsdwPendingWeaponItems: {},
    rsdwHydrationToken: 0,
    rsdwHydrationError: '',
    pendingDirectoryJoin: null,
    rsdwToolkitLoading: false,
    rsdwSourceBusy: false,
    rsdwRuntimeAssets: null,
    rsdwRuntimeAssetFilter: false,
    serverActivityFilter: 'all',
    serverActivitySearch: '',
    rsdwSource: { mode: 'remote', baseUrl: 'https://rsdwtools.com/', revision: '', toolkitValid: false },
  };

  const CHARACTER_BACKDROPS = Object.freeze([
    { value:'backdrop-beach', label:'Beach', file:'placards/6.webp' },
    { value:'backdrop-desert', label:'Desert', file:'placards/8.webp' },
    { value:'backdrop-forest', label:'Forest', file:'placards/5.webp' },
    { value:'backdrop-graveyard', label:'Graveyard', file:'placards/9.webp' },
    { value:'backdrop-tavern', label:'Tavern', file:'placards/7.webp' },
  ]);
  const CHARACTER_BACKGROUND_STYLES = Object.freeze([
    { value:'theme', label:'Theme', surface:'linear-gradient(135deg,#17201d,#080b0b)' },
    { value:'studio', label:'Studio', surface:'#34383d' },
    { value:'forest', label:'Forest green', surface:'#173426' },
    { value:'parchment', label:'Parchment', surface:'#d7c39d' },
    { value:'black', label:'Black', surface:'#000000' },
    { value:'white', label:'White', surface:'#ffffff' },
    { value:'twilight', label:'Twilight', surface:'radial-gradient(circle at 72% 22%,#95734d 0 2%,transparent 18%),linear-gradient(155deg,#111b2b,#26364b 48%,#13181b)' },
    { value:'embers', label:'Ember Hall', surface:'radial-gradient(circle at 50% 110%,#c15a25,transparent 38%),linear-gradient(145deg,#28130d,#090706 70%)' },
    { value:'aurora', label:'Aurora', surface:'radial-gradient(ellipse at 30% 18%,rgba(75,218,165,.72),transparent 28%),radial-gradient(ellipse at 72% 24%,rgba(73,132,219,.65),transparent 30%),linear-gradient(#07131d,#10242a)' },
    { value:'runic', label:'Runic Gold', surface:'repeating-radial-gradient(circle at 50% 48%,transparent 0 32px,rgba(225,181,87,.18) 34px 36px),linear-gradient(135deg,#18150d,#080b0b)' },
  ]);
  const characterBackdropDataUrls = new Map();

  function characterBackdropUrl(value) {
    const backdrop=CHARACTER_BACKDROPS.find((entry)=>entry.value===String(value||''));
    return backdrop?new URL(`assets/${backdrop.file}`,document.baseURI).href:'';
  }

  function characterBackdropFile(value) {
    const backdrop=CHARACTER_BACKDROPS.find((entry)=>entry.value===String(value||''));
    return backdrop?`assets/${backdrop.file}`:'';
  }

  async function characterBackdropDataUrl(value) {
    const url=characterBackdropUrl(value);
    if(!url)return '';
    if(characterBackdropDataUrls.has(url))return characterBackdropDataUrls.get(url);
    try{
      const asset=await window.dragonwilds?.readRendererAsset?.(characterBackdropFile(value));
      const dataUrl=String(asset?.dataUrl||'');
      if(dataUrl.startsWith('data:')){characterBackdropDataUrls.set(url,dataUrl);return dataUrl;}
    }catch(_){/* use the served-origin fallback below */}
    return await new Promise((resolve)=>{
      const image=new Image();
      image.onload=()=>{try{const canvas=document.createElement('canvas');canvas.width=image.naturalWidth;canvas.height=image.naturalHeight;canvas.getContext('2d').drawImage(image,0,0);const dataUrl=canvas.toDataURL('image/png');characterBackdropDataUrls.set(url,dataUrl);resolve(dataUrl);}catch(_){resolve('');}};
      image.onerror=()=>resolve('');
      image.src=url;
    });
  }

  function characterBackgroundScript(value, embeddedImageUrl = '') {
    const mode=String(value||'theme');
    const candidate=String(embeddedImageUrl||'');
    const imageUrl=/^(data:|https?:)/i.test(candidate)?candidate:'';
    const theme=(state.data?.application?.theme||'dark')==='light'?'#eee8dc':'#050708';
    const style=CHARACTER_BACKGROUND_STYLES.find((entry)=>entry.value===mode);
    const fallbackSurface=mode==='theme'?theme:(style?.surface||theme);
    return `(()=>{const imageUrl=${JSON.stringify(imageUrl)};const fallback=${JSON.stringify(fallbackSurface)};const surface=imageUrl?'linear-gradient(rgba(3,5,5,.06),rgba(3,5,5,.2)),url("'+imageUrl.replace(/"/g,'%22')+'") center/cover no-repeat':fallback;document.documentElement.style.background=fallback;document.body.style.setProperty('background',fallback,'important');document.body.style.isolation='isolate';let backdrop=document.querySelector('#dws-avatar-backdrop');if(!backdrop){backdrop=document.createElement('div');backdrop.id='dws-avatar-backdrop';document.body.prepend(backdrop);}Object.assign(backdrop.style,{position:'fixed',inset:'0',zIndex:'9997',pointerEvents:'none',background:surface,backgroundPosition:'center',backgroundSize:'cover',backgroundRepeat:'no-repeat'});const stage=document.querySelector('#avatar-stage');if(stage){stage.style.setProperty('background','transparent','important');stage.style.zIndex='9998';}document.querySelectorAll('canvas').forEach((canvas)=>{canvas.style.setProperty('background','transparent','important');canvas.style.mixBlendMode=imageUrl?'screen':'normal';canvas.style.position='relative';canvas.style.zIndex='9999';});return {ok:true,image:!!imageUrl,canvases:document.querySelectorAll('canvas').length,stage:!!stage};})()`;
  }

  const CHARACTER_PORTRAITS = [
    'female_auburn_ponytail.png','female_braided_chestnut.png','female_dark_curls.png',
    'female_short_black_bob.png','female_silver_pixie.png','female_wavy_blonde.png',
    'female_teal_battlemage_braids.png','female_cobalt_warrior_ponytail.png',
    'male_blond_undercut.png','male_cropped_auburn.png','male_dark_curls.png',
    'male_short_tousled_brown.png','male_shoulder_black.png','male_silver_tied_back.png',
    'male_forest_ranger_dreadlocks.png','androgynous_burgundy_battlemage.png',
  ];
  const portraitAsset = (name) => `assets/character-portraits/${encodeURIComponent(name)}`;
  const PLATFORM_LOGOS = {steam:'assets/platforms/steam.svg',epic:'assets/platforms/epicgames.svg',xbox:'assets/platforms/xbox.svg',playstation:'assets/platforms/playstation.svg',nintendo:'assets/platforms/nintendo.svg',discord:'assets/platforms/discord.svg',nexus:'assets/platforms/nexusmods.svg',windows:'assets/platforms/windows.svg',linux:'assets/platforms/linux.svg'};
  const PLACARD_BACKGROUNDS = ['1','2','3','4','5','6','7','8','9'];
  const PLACARD_BACKGROUND_LABELS = Object.freeze({1:'Ashen Gold',2:'Deep Forest',3:'Runic Stone',4:'Ember Keep',5:'Wild Forest',6:'Coastal Dawn',7:'Warm Tavern',8:'Desert Ruins',9:'Graveyard Mist'});
  const platformLogo = (key,label) => {
    const name=String(label||key);
    return PLATFORM_LOGOS[key]
      ? `<span class="platform-logo-shell platform-${escapeHtml(key)}"><img class="platform-logo" src="${PLATFORM_LOGOS[key]}" alt="${escapeHtml(name)}"/><b class="platform-logo-fallback" aria-hidden="true">${escapeHtml(String(key).toUpperCase().slice(0,4))}</b></span>`
      : `<b class="platform-logo-fallback visible">${escapeHtml(name.slice(0,4))}</b>`;
  };
  const assetDataUrl = async (url) => {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`Portrait asset could not be loaded (${response.status}).`);
    const blob = await response.blob();
    return await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result||''));reader.onerror=()=>reject(reader.error||new Error('Portrait conversion failed.'));reader.readAsDataURL(blob);});
  };

  const I18N = {
    en:{worldLauncher:'World Launcher',play:'Play',privateWorlds:'Private Worlds',worlds:'Worlds',host:'Host',servers:'Servers',remoteServer:'Remote Server',profile:'Profile',system:'System',help:'Help',settings:'Settings',playerProfile:'Player Profile',notifications:'Notifications',expandNavigation:'Expand navigation',collapseNavigation:'Collapse navigation',back:'Back to previous area',minimize:'Minimize',maximize:'Maximize / Restore',close:'Close',overview:'Overview',players:'Players',map:'Map',spawner:'Spawner',worldSave:'World Save',mods:'Mods',broadcast:'Broadcast',networking:'Networking',maintenance:'Maintenance',feedback:'Feedback',configuration:'Configuration',activity:'Activity',userProfile:'User Profile',characters:'Characters',liveMap:'Live Map & Tracking',ledger:'Ledger',characterMap:'Character Map',client:'Client',server:'Server',application:'Application',webHosting:'WebHost',integrations:'Integrations',about:'About',network:'Network',storage:'Storage',tags:'Tags',editTags:'Edit Tags'},
    fr:{worldLauncher:'Lanceur de mondes',play:'Jouer',privateWorlds:'Mondes privés',worlds:'Mondes',host:'Héberger',servers:'Serveurs',remoteServer:'Serveur distant',profile:'Profil',system:'Système',help:'Aide',settings:'Paramètres',playerProfile:'Profil du joueur',notifications:'Notifications',expandNavigation:'Développer la navigation',collapseNavigation:'Réduire la navigation',back:'Zone précédente',minimize:'Réduire',maximize:'Agrandir / Restaurer',close:'Fermer',overview:'Aperçu',players:'Joueurs',map:'Carte',spawner:'Générateur',worldSave:'Sauvegarde du monde',mods:'Mods',broadcast:'Diffusion',networking:'Réseau',maintenance:'Maintenance',feedback:'Avis',configuration:'Configuration',activity:'Activité',userProfile:'Profil utilisateur',characters:'Personnages',liveMap:'Carte et suivi en direct',ledger:'Registre',characterMap:'Carte du personnage',client:'Client',server:'Serveur',application:'Application',webHosting:'Hébergement Web',integrations:'Intégrations',about:'À propos',network:'Réseau',storage:'Stockage',tags:'Tags',editTags:'Modifier les tags'},
    de:{worldLauncher:'Welten-Launcher',play:'Spielen',privateWorlds:'Private Welten',worlds:'Welten',host:'Hosten',servers:'Server',remoteServer:'Remote-Server',profile:'Profil',system:'System',help:'Hilfe',settings:'Einstellungen',playerProfile:'Spielerprofil',notifications:'Benachrichtigungen',expandNavigation:'Navigation erweitern',collapseNavigation:'Navigation einklappen',back:'Zum vorherigen Bereich',minimize:'Minimieren',maximize:'Maximieren / Wiederherstellen',close:'Schließen',overview:'Übersicht',players:'Spieler',map:'Karte',spawner:'Spawner',worldSave:'Weltspielstand',mods:'Mods',broadcast:'Übertragung',networking:'Netzwerk',maintenance:'Wartung',feedback:'Feedback',configuration:'Konfiguration',activity:'Aktivität',userProfile:'Benutzerprofil',characters:'Charaktere',liveMap:'Live-Karte & Verfolgung',ledger:'Chronik',characterMap:'Charakterkarte',client:'Client',server:'Server',application:'Anwendung',webHosting:'Webhosting',integrations:'Integrationen',about:'Info',network:'Netzwerk',storage:'Speicher',tags:'Tags',editTags:'Tags bearbeiten'},
    es:{worldLauncher:'Lanzador de mundos',play:'Jugar',privateWorlds:'Mundos privados',worlds:'Mundos',host:'Alojar',servers:'Servidores',remoteServer:'Servidor remoto',profile:'Perfil',system:'Sistema',help:'Ayuda',settings:'Ajustes',playerProfile:'Perfil del jugador',notifications:'Notificaciones',expandNavigation:'Expandir navegación',collapseNavigation:'Contraer navegación',back:'Área anterior',minimize:'Minimizar',maximize:'Maximizar / Restaurar',close:'Cerrar',overview:'Resumen',players:'Jugadores',map:'Mapa',spawner:'Generador',worldSave:'Guardado del mundo',mods:'Mods',broadcast:'Difusión',networking:'Red',maintenance:'Mantenimiento',feedback:'Comentarios',configuration:'Configuración',activity:'Actividad',userProfile:'Perfil de usuario',characters:'Personajes',liveMap:'Mapa y seguimiento en vivo',ledger:'Registro',characterMap:'Mapa del personaje',client:'Cliente',server:'Servidor',application:'Aplicación',webHosting:'Alojamiento web',integrations:'Integraciones',about:'Acerca de',network:'Red',storage:'Almacenamiento',tags:'Etiquetas',editTags:'Editar etiquetas'},
    it:{worldLauncher:'Launcher dei mondi',play:'Gioca',privateWorlds:'Mondi privati',worlds:'Mondi',host:'Ospita',servers:'Server',remoteServer:'Server remoto',profile:'Profilo',system:'Sistema',help:'Aiuto',settings:'Impostazioni',playerProfile:'Profilo giocatore',notifications:'Notifiche',expandNavigation:'Espandi navigazione',collapseNavigation:'Comprimi navigazione',back:'Area precedente',minimize:'Riduci',maximize:'Ingrandisci / Ripristina',close:'Chiudi',overview:'Panoramica',players:'Giocatori',map:'Mappa',spawner:'Generatore',worldSave:'Salvataggio mondo',mods:'Mod',broadcast:'Trasmissione',networking:'Rete',maintenance:'Manutenzione',feedback:'Feedback',configuration:'Configurazione',activity:'Attività',userProfile:'Profilo utente',characters:'Personaggi',liveMap:'Mappa e tracciamento live',ledger:'Registro',characterMap:'Mappa personaggio',client:'Client',server:'Server',application:'Applicazione',webHosting:'Hosting web',integrations:'Integrazioni',about:'Informazioni',network:'Rete',storage:'Archiviazione',tags:'Tag',editTags:'Modifica tag'}
  };
  const languageCode = () => ['en','fr','de','es','it'].includes(String(state.data?.application?.language||'en')) ? String(state.data.application.language) : 'en';
  const t = (key) => I18N[languageCode()]?.[key] || I18N.en[key] || key;
  const WORLD_I18N = {
    en:{eyebrow:'Discover · Connect · Synchronize',subtitle:'Browse favorited and previously connected Worlds.',open:'Open in Window',lan:'LAN Scan',refresh:'Refresh',importWorld:'Import .dwsworld',importProfile:'Import .rsdwl',exportProfile:'Export Profile',direct:'Favorites',directSub:'Favorited Worlds and saved Direct Connect profiles',manifest:'Public Server List',manifestSub:'Live launcher-broadcast Worlds with native Join handoff',public:'Sync Directory',publicSub:'Fingerprint-verified Worlds only',search:'Search Worlds, tags, region, mods…',all:'All',favorites:'Favorites',recent:'Recently Played',sort:'Sort',recommended:'Recommended',lowPing:'Lowest ping',mostPlayers:'Most players',bestHealth:'Best health',recentlyUsed:'Recently used',name:'Name A–Z',worldType:'World type',allTypes:'All types',gameMode:'Game mode',allModes:'All modes',host:'Host',allHosts:'All hosts',tag:'Tag',allTags:'All tags',clear:'Clear selectors',showing:'Showing',of:'of',seven:'ten per page',previous:'Previous',next:'Next',page:'Page',sessions:'sessions available',every30:'refreshes every 30 seconds',noWorlds:'No Worlds match this view yet.',cards:'Cards',horizontal:'Horizontal'},
    fr:{eyebrow:'Découvrir · Connecter · Synchroniser',subtitle:'Parcourez les sessions Dragonwilds en direct ou conservez les connexions IP dans un espace de connexion directe distinct.',open:'Ouvrir dans une fenêtre',lan:'Analyse LAN',refresh:'Actualiser',importWorld:'Importer .dwsworld',importProfile:'Importer .rsdwl',exportProfile:'Exporter le profil',direct:'Déjà invoqués',directSub:'Adresses enregistrées et profils de connexion directe importés',manifest:'Manifestes',manifestSub:'Mondes de sites Web dont le fingerprint est vérifié',public:'Grand Ashenfall',publicSub:'Découverte publique native enrichie par Sync',search:'Rechercher mondes, tags, région, mods…',all:'Tous',favorites:'Favoris',recent:'Joués récemment',sort:'Trier',recommended:'Recommandés',lowPing:'Ping le plus faible',mostPlayers:'Plus de joueurs',bestHealth:'Meilleure santé',recentlyUsed:'Utilisés récemment',name:'Nom A–Z',worldType:'Type de monde',allTypes:'Tous les types',gameMode:'Mode de jeu',allModes:'Tous les modes',host:'Hôte',allHosts:'Tous les hôtes',tag:'Tag',allTags:'Tous les tags',clear:'Effacer les filtres',showing:'Affichage',of:'sur',seven:'sept par page',previous:'Précédent',next:'Suivant',page:'Page',sessions:'sessions disponibles',every30:'actualisation toutes les 30 secondes',noWorlds:'Aucun monde ne correspond à cette vue.',cards:'Placards',horizontal:'Horizontal'},
    de:{eyebrow:'Entdecken · Verbinden · Synchronisieren',subtitle:'Durchsuchen Sie aktive Dragonwilds-Sitzungen oder verwalten Sie gespeicherte IP-Verbindungen getrennt.',open:'In Fenster öffnen',lan:'LAN-Suche',refresh:'Aktualisieren',importWorld:'.dwsworld importieren',importProfile:'.rsdwl importieren',exportProfile:'Profil exportieren',direct:'Früher beschworen',directSub:'Gespeicherte Adressen und importierte Direktverbindungsprofile',manifest:'Manifest',manifestSub:'Fingerprint-geprüfte Website-Welten',public:'Großes Ashenfall',publicSub:'Native öffentliche Suche mit Sync-Erweiterung',search:'Welten, Tags, Region, Mods suchen…',all:'Alle',favorites:'Favoriten',recent:'Kürzlich gespielt',sort:'Sortieren',recommended:'Empfohlen',lowPing:'Niedrigster Ping',mostPlayers:'Meiste Spieler',bestHealth:'Bester Zustand',recentlyUsed:'Zuletzt verwendet',name:'Name A–Z',worldType:'Welttyp',allTypes:'Alle Typen',gameMode:'Spielmodus',allModes:'Alle Modi',host:'Host',allHosts:'Alle Hosts',tag:'Tag',allTags:'Alle Tags',clear:'Filter löschen',showing:'Anzeige',of:'von',seven:'sieben pro Seite',previous:'Zurück',next:'Weiter',page:'Seite',sessions:'Sitzungen verfügbar',every30:'Aktualisierung alle 30 Sekunden',noWorlds:'Keine Welten entsprechen dieser Ansicht.',cards:'Karten',horizontal:'Horizontal'},
    es:{eyebrow:'Descubrir · Conectar · Sincronizar',subtitle:'Explora sesiones activas de Dragonwilds o conserva conexiones IP en un espacio separado de conexión directa.',open:'Abrir en ventana',lan:'Explorar LAN',refresh:'Actualizar',importWorld:'Importar .dwsworld',importProfile:'Importar .rsdwl',exportProfile:'Exportar perfil',direct:'Invocados anteriormente',directSub:'Direcciones guardadas y perfiles de conexión directa importados',manifest:'Manifiesto',manifestSub:'Mundos web con huella verificada',public:'Gran Ashenfall',publicSub:'Descubrimiento público nativo mejorado con Sync',search:'Buscar mundos, etiquetas, región, mods…',all:'Todos',favorites:'Favoritos',recent:'Jugados recientemente',sort:'Ordenar',recommended:'Recomendados',lowPing:'Ping más bajo',mostPlayers:'Más jugadores',bestHealth:'Mejor salud',recentlyUsed:'Usados recientemente',name:'Nombre A–Z',worldType:'Tipo de mundo',allTypes:'Todos los tipos',gameMode:'Modo de juego',allModes:'Todos los modos',host:'Host',allHosts:'Todos los hosts',tag:'Etiqueta',allTags:'Todas las etiquetas',clear:'Borrar filtros',showing:'Mostrando',of:'de',seven:'siete por página',previous:'Anterior',next:'Siguiente',page:'Página',sessions:'sesiones disponibles',every30:'se actualiza cada 30 segundos',noWorlds:'Ningún mundo coincide con esta vista.',cards:'Tarjetas',horizontal:'Horizontal'},
    it:{eyebrow:'Scopri · Connetti · Sincronizza',subtitle:'Sfoglia le sessioni Dragonwilds live o conserva le connessioni IP in uno spazio Connessione diretta separato.',open:'Apri in finestra',lan:'Scansione LAN',refresh:'Aggiorna',importWorld:'Importa .dwsworld',importProfile:'Importa .rsdwl',exportProfile:'Esporta profilo',direct:'Evocati in precedenza',directSub:'Indirizzi salvati e profili di connessione diretta importati',manifest:'Manifest',manifestSub:'Mondi Web con fingerprint verificato',public:'Grande Ashenfall',publicSub:'Scoperta pubblica nativa con miglioramenti Sync',search:'Cerca mondi, tag, regione, mod…',all:'Tutti',favorites:'Preferiti',recent:'Giocati di recente',sort:'Ordina',recommended:'Consigliati',lowPing:'Ping più basso',mostPlayers:'Più giocatori',bestHealth:'Stato migliore',recentlyUsed:'Usati di recente',name:'Nome A–Z',worldType:'Tipo di mondo',allTypes:'Tutti i tipi',gameMode:'Modalità di gioco',allModes:'Tutte le modalità',host:'Host',allHosts:'Tutti gli host',tag:'Tag',allTags:'Tutti i tag',clear:'Cancella filtri',showing:'Visualizzazione',of:'di',seven:'sette per pagina',previous:'Precedente',next:'Successivo',page:'Pagina',sessions:'sessioni disponibili',every30:'aggiornamento ogni 30 secondi',noWorlds:'Nessun mondo corrisponde a questa vista.',cards:'Schede',horizontal:'Orizzontale'}
  };
  const wt = (key) => WORLD_I18N[languageCode()]?.[key] || WORLD_I18N.en[key] || key;
  const EDITOR_I18N = {
    en:{characterAppearance:'Character & Appearance',itemEditor:'Item Editor',spellEditor:'Spell Editor',recipeUnlocker:'Recipe Unlocker',questEditor:'Quest Editor',identity:'Identity',characterIdentity:'Character identity',playerName:'Player name',characterType:'Character type',characterGuid:'Character GUID',appearance:'Appearance',rebuildCharacter:'Rebuild character',bodyType:'Body type',head:'Head',hair:'Hair',facialHair:'Facial hair',skinTone:'Skin tone',hairColor:'Hair color',eyeColor:'Eye color',eyebrowColor:'Eyebrow color',survival:'Survival',characterUpkeep:'Character upkeep',keepFull:'Keep full',progression:'Progression',skills:'Skills',travelWorld:'Travel & World',mountsMap:'Mounts and map',equippedMount:'Equipped mount',noMount:'No mount',revealMap:'Reveal full Ashenfall map',reputation:'Reputation',vendors:'Vendors',itemBrowser:'Item Browser',playerInventory:'Player Inventory',bagItems:'Bag Items',runeItems:'Rune Items',ammoItems:'Ammo Items',questItems:'Quest Items',searchItems:'Search items…',previous:'Previous',next:'Next',page:'Page',of:'of',actionBar:'Action bar',equipment:'Equipment',personalStorage:'Personal storage',rightClick:'Right-click an item for actions',emptySlot:'Empty slot',setMax:'Set Max',duplicate:'Dupe',customAmount:'Custom Amount',repair:'Repair',remove:'Remove',add:'Add',addMax:'Add Max',quantity:'Quantity',cancel:'Cancel',apply:'Apply',saveCharacter:'Save to Character',readyNative:'Ready',loading:'Loading',search:'Search',complete:'Complete',incomplete:'Incomplete',mainQuests:'Main quests',sideQuests:'Side quests',fullBody:'Full body',face:'Face'},
    fr:{characterAppearance:'Personnage et apparence',itemEditor:'Éditeur d’objets',spellEditor:'Éditeur de sorts',recipeUnlocker:'Déblocage de recettes',questEditor:'Éditeur de quêtes',identity:'Identité',characterIdentity:'Identité du personnage',playerName:'Nom du joueur',characterType:'Type de personnage',characterGuid:'GUID du personnage',appearance:'Apparence',rebuildCharacter:'Reconstruire le personnage',bodyType:'Type de corps',head:'Tête',hair:'Cheveux',facialHair:'Barbe',skinTone:'Teint',hairColor:'Couleur des cheveux',eyeColor:'Couleur des yeux',eyebrowColor:'Couleur des sourcils',survival:'Survie',characterUpkeep:'Besoins du personnage',keepFull:'Maintenir plein',progression:'Progression',skills:'Compétences',travelWorld:'Voyage et monde',mountsMap:'Montures et carte',equippedMount:'Monture équipée',noMount:'Aucune monture',revealMap:'Révéler toute la carte d’Ashenfall',reputation:'Réputation',vendors:'Marchands',itemBrowser:'Catalogue d’objets',playerInventory:'Inventaire du joueur',bagItems:'Objets du sac',runeItems:'Runes',ammoItems:'Munitions',questItems:'Objets de quête',searchItems:'Rechercher des objets…',previous:'Précédent',next:'Suivant',page:'Page',of:'sur',actionBar:'Barre d’action',equipment:'Équipement',personalStorage:'Stockage personnel',rightClick:'Clic droit sur un objet pour les actions',emptySlot:'Emplacement vide',setMax:'Maximum',duplicate:'Dupliquer',customAmount:'Quantité personnalisée',repair:'Réparer',remove:'Retirer',add:'Ajouter',addMax:'Ajouter au maximum',quantity:'Quantité',cancel:'Annuler',apply:'Appliquer',saveCharacter:'Enregistrer le personnage',readyNative:'Prêt · éditeur natif chargé depuis le module RSDW actuel',loading:'Chargement',search:'Rechercher',complete:'Terminée',incomplete:'Incomplète',mainQuests:'Quêtes principales',sideQuests:'Quêtes secondaires',fullBody:'Corps entier',face:'Visage'},
    de:{characterAppearance:'Charakter & Aussehen',itemEditor:'Gegenstandseditor',spellEditor:'Zaubereditor',recipeUnlocker:'Rezeptfreischaltung',questEditor:'Questeditor',identity:'Identität',characterIdentity:'Charakteridentität',playerName:'Spielername',characterType:'Charaktertyp',characterGuid:'Charakter-GUID',appearance:'Aussehen',rebuildCharacter:'Charakter neu gestalten',bodyType:'Körpertyp',head:'Kopf',hair:'Haare',facialHair:'Bart',skinTone:'Hautton',hairColor:'Haarfarbe',eyeColor:'Augenfarbe',eyebrowColor:'Augenbrauenfarbe',survival:'Überleben',characterUpkeep:'Charakterversorgung',keepFull:'Voll halten',progression:'Fortschritt',skills:'Fertigkeiten',travelWorld:'Reise & Welt',mountsMap:'Reittiere und Karte',equippedMount:'Ausgerüstetes Reittier',noMount:'Kein Reittier',revealMap:'Gesamte Ashenfall-Karte aufdecken',reputation:'Ruf',vendors:'Händler',itemBrowser:'Gegenstandskatalog',playerInventory:'Spielerinventar',bagItems:'Taschengegenstände',runeItems:'Runen',ammoItems:'Munition',questItems:'Questgegenstände',searchItems:'Gegenstände suchen…',previous:'Zurück',next:'Weiter',page:'Seite',of:'von',actionBar:'Aktionsleiste',equipment:'Ausrüstung',personalStorage:'Persönlicher Speicher',rightClick:'Rechtsklick auf einen Gegenstand für Aktionen',emptySlot:'Leerer Platz',setMax:'Maximum',duplicate:'Duplizieren',customAmount:'Eigene Menge',repair:'Reparieren',remove:'Entfernen',add:'Hinzufügen',addMax:'Maximum hinzufügen',quantity:'Menge',cancel:'Abbrechen',apply:'Anwenden',saveCharacter:'Im Charakter speichern',readyNative:'Bereit · nativer Editor aus dem aktuellen RSDW-Modul geladen',loading:'Laden',search:'Suchen',complete:'Abgeschlossen',incomplete:'Unvollständig',mainQuests:'Hauptquests',sideQuests:'Nebenquests',fullBody:'Ganzkörper',face:'Gesicht'},
    es:{characterAppearance:'Personaje y apariencia',itemEditor:'Editor de objetos',spellEditor:'Editor de hechizos',recipeUnlocker:'Desbloqueo de recetas',questEditor:'Editor de misiones',identity:'Identidad',characterIdentity:'Identidad del personaje',playerName:'Nombre del jugador',characterType:'Tipo de personaje',characterGuid:'GUID del personaje',appearance:'Apariencia',rebuildCharacter:'Reconstruir personaje',bodyType:'Tipo de cuerpo',head:'Cabeza',hair:'Cabello',facialHair:'Barba',skinTone:'Tono de piel',hairColor:'Color del cabello',eyeColor:'Color de ojos',eyebrowColor:'Color de cejas',survival:'Supervivencia',characterUpkeep:'Necesidades del personaje',keepFull:'Mantener lleno',progression:'Progresión',skills:'Habilidades',travelWorld:'Viaje y mundo',mountsMap:'Monturas y mapa',equippedMount:'Montura equipada',noMount:'Sin montura',revealMap:'Revelar todo el mapa de Ashenfall',reputation:'Reputación',vendors:'Vendedores',itemBrowser:'Catálogo de objetos',playerInventory:'Inventario del jugador',bagItems:'Objetos de bolsa',runeItems:'Runas',ammoItems:'Munición',questItems:'Objetos de misión',searchItems:'Buscar objetos…',previous:'Anterior',next:'Siguiente',page:'Página',of:'de',actionBar:'Barra de acción',equipment:'Equipo',personalStorage:'Almacenamiento personal',rightClick:'Clic derecho en un objeto para ver acciones',emptySlot:'Espacio vacío',setMax:'Máximo',duplicate:'Duplicar',customAmount:'Cantidad personalizada',repair:'Reparar',remove:'Eliminar',add:'Añadir',addMax:'Añadir máximo',quantity:'Cantidad',cancel:'Cancelar',apply:'Aplicar',saveCharacter:'Guardar en personaje',readyNative:'Listo · editor nativo cargado desde el módulo RSDW actual',loading:'Cargando',search:'Buscar',complete:'Completada',incomplete:'Incompleta',mainQuests:'Misiones principales',sideQuests:'Misiones secundarias',fullBody:'Cuerpo entero',face:'Rostro'},
    it:{characterAppearance:'Personaggio e aspetto',itemEditor:'Editor oggetti',spellEditor:'Editor incantesimi',recipeUnlocker:'Sblocco ricette',questEditor:'Editor missioni',identity:'Identità',characterIdentity:'Identità personaggio',playerName:'Nome giocatore',characterType:'Tipo personaggio',characterGuid:'GUID personaggio',appearance:'Aspetto',rebuildCharacter:'Ricostruisci personaggio',bodyType:'Tipo di corpo',head:'Testa',hair:'Capelli',facialHair:'Barba',skinTone:'Tonalità pelle',hairColor:'Colore capelli',eyeColor:'Colore occhi',eyebrowColor:'Colore sopracciglia',survival:'Sopravvivenza',characterUpkeep:'Bisogni personaggio',keepFull:'Mantieni pieno',progression:'Progressione',skills:'Abilità',travelWorld:'Viaggio e mondo',mountsMap:'Cavalcature e mappa',equippedMount:'Cavalcatura equipaggiata',noMount:'Nessuna cavalcatura',revealMap:'Rivela tutta la mappa di Ashenfall',reputation:'Reputazione',vendors:'Mercanti',itemBrowser:'Catalogo oggetti',playerInventory:'Inventario giocatore',bagItems:'Oggetti borsa',runeItems:'Rune',ammoItems:'Munizioni',questItems:'Oggetti missione',searchItems:'Cerca oggetti…',previous:'Precedente',next:'Successivo',page:'Pagina',of:'di',actionBar:'Barra azioni',equipment:'Equipaggiamento',personalStorage:'Deposito personale',rightClick:'Clic destro su un oggetto per le azioni',emptySlot:'Slot vuoto',setMax:'Massimo',duplicate:'Duplica',customAmount:'Quantità personalizzata',repair:'Ripara',remove:'Rimuovi',add:'Aggiungi',addMax:'Aggiungi massimo',quantity:'Quantità',cancel:'Annulla',apply:'Applica',saveCharacter:'Salva nel personaggio',readyNative:'Pronto · editor nativo caricato dal modulo RSDW corrente',loading:'Caricamento',search:'Cerca',complete:'Completata',incomplete:'Incompleta',mainQuests:'Missioni principali',sideQuests:'Missioni secondarie',fullBody:'Corpo intero',face:'Viso'}
  };
  const EDITOR_DETAIL_I18N = {
    en:{characterSubtitle:'Identity, save fields, skills & unlocks',itemSubtitle:'Inventory, equipment & item changes',spellSubtitle:'Spellbooks and unlocked spells',recipeSubtitle:'Browse and unlock recipes',questSubtitle:'Quest completion state',writtenToSave:'Written to the save, not a launcher-only label',refreshesPreview:'Appearance is written to the save; visual customization can also be completed in Dragonwilds.',setValueKeepFull:'Set a value or keep that meter full',hydration:'Hydration',sustenance:'Sustenance',endurance:'Endurance',infiniteDecay:'Infinite decay buffer',normalDecay:'Normal decay',catalogSkills:'RSDW catalog skills',experience:'Experience',mountsUnlocked:'mounts unlocked',oneWayUnlock:'This is a one-way RSDW save unlock.',currentVendors:'current catalog vendors',tiers:'Tiers',suppliesFields:'RSDWTools supplies current save-field definitions and catalog values.',suppliesUi:'Dragonwilds Sync supplies the native UI, validation, backup, and direct writeback.',loadedAutomatically:'is loaded automatically. Dragonwilds Sync owns backup-first writeback.',hydrating:'Loading',loadingCatalog:'Loading the current RSDW catalog and matching it to this character save…',selectedUnlocked:'Selected and unlocked spells',spellbookUsed:'spellbook slots used',recipes:'Recipes',unlocked:'unlocked',available:'available',questCompletion:'Quest completion',known:'known',charactersPageSubtitle:'Combat identity, character summary, and every RSDW editor now share one workspace.',openInWindow:'Open in Window',refreshUpstream:'Check for RSDW Updates',hydrateLocal:'Load Character Tools',importProfile:'Import .rsdwl',exportCharacter:'Export Character',livePreview:'Character Preview',selectedCharacter:'Selected Character',combatIdentity:'Combat identity',combatHelp:'Tags organize this character. Applying its template replaces only head, body, and leg armour using the current RSDW item catalog.',archetype:'Archetype',subtype:'Subtype',saveTags:'Save Tags',previewInject:'Preview & Inject Armour',lastModified:'Last modified',saveSize:'Save size',profileStatus:'Profile status',worldAssociations:'World associations',chooseImage:'Choose Image',favorite:'Favorite',removeFavorite:'Remove Favorite',cloneCharacter:'Clone Character',deleteCharacter:'Delete Character',editorHint:'Select an editor here. Editing dialogs stay inside Dragonwilds Sync and can be moved, resized, minimized, maximized, or closed from the in-app taskbar.',captureFace:'Capture Face Card',openAvatar:'Open Full Avatar',avatarGestures:'Drag to orbit · wheel or pinch to zoom · right-drag to pan'},
    fr:{characterSubtitle:'Identité, corps, visage, couleurs, compétences et déblocages',itemSubtitle:'Inventaire, équipement et modifications d’objets',spellSubtitle:'Grimoires et sorts débloqués',recipeSubtitle:'Parcourir et débloquer les recettes',questSubtitle:'Progression des quêtes',writtenToSave:'Écrit dans la sauvegarde, pas seulement dans le lanceur',refreshesPreview:'Chaque modification actualise l’aperçu 3D ci-dessus',setValueKeepFull:'Définissez une valeur ou maintenez la jauge pleine',hydration:'Hydratation',sustenance:'Nourriture',endurance:'Endurance',infiniteDecay:'Décroissance infinie',normalDecay:'Décroissance normale',catalogSkills:'compétences du catalogue RSDW',experience:'Expérience',mountsUnlocked:'montures débloquées',oneWayUnlock:'Ceci est un déblocage irréversible de la sauvegarde RSDW.',currentVendors:'marchands du catalogue actuel',tiers:'Paliers',suppliesFields:'RSDWTools fournit les champs de sauvegarde et les valeurs de catalogue actuels.',suppliesUi:'Dragonwilds Sync fournit l’interface native, l’aperçu en direct, la validation, la sauvegarde et l’écriture directe.',loadedAutomatically:'est chargé automatiquement. Dragonwilds Sync gère l’écriture avec sauvegarde préalable.',hydrating:'Chargement de',loadingCatalog:'Chargement du catalogue RSDW actuel et association avec cette sauvegarde…',selectedUnlocked:'Sorts sélectionnés et débloqués',spellbookUsed:'emplacements de grimoire utilisés',recipes:'Recettes',unlocked:'débloquées',available:'disponibles',questCompletion:'Progression des quêtes',known:'connues',charactersPageSubtitle:'Le personnage sélectionné alimente chaque éditeur RSDW et l’avatar 3D.',openInWindow:'Ouvrir dans une fenêtre',refreshUpstream:'Actualiser la source',hydrateLocal:'Charger les outils locaux',importProfile:'Importer .rsdwl',exportCharacter:'Exporter le personnage',livePreview:'Aperçu 3D du personnage',selectedCharacter:'Personnage sélectionné',combatIdentity:'Identité de combat',combatHelp:'Les tags organisent ce personnage. Le modèle ne remplace que l’armure de tête, de corps et de jambes.',archetype:'Archétype',subtype:'Sous-type',saveTags:'Enregistrer les tags',previewInject:'Aperçu et injection d’armure',lastModified:'Dernière modification',saveSize:'Taille de sauvegarde',profileStatus:'État du profil',worldAssociations:'Mondes associés',chooseImage:'Choisir une image',favorite:'Favori',removeFavorite:'Retirer des favoris',cloneCharacter:'Cloner le personnage',deleteCharacter:'Supprimer le personnage',editorHint:'Sélectionnez un éditeur · clic droit pour l’ouvrir dans une fenêtre dédiée.',captureFace:'Capturer le portrait',openAvatar:'Ouvrir l’avatar complet',avatarGestures:'Glisser pour tourner · molette ou pincement pour zoomer · clic droit pour déplacer'},
    de:{characterSubtitle:'Identität, Körper, Gesicht, Farben, Fertigkeiten und Freischaltungen',itemSubtitle:'Inventar-, Ausrüstungs- und Gegenstandsänderungen',spellSubtitle:'Zauberbücher und freigeschaltete Zauber',recipeSubtitle:'Rezepte durchsuchen und freischalten',questSubtitle:'Questfortschritt',writtenToSave:'Wird in den Spielstand geschrieben, nicht nur im Launcher angezeigt',refreshesPreview:'Jede Änderung aktualisiert die 3D-Vorschau oben',setValueKeepFull:'Wert setzen oder Anzeige voll halten',hydration:'Hydration',sustenance:'Nahrung',endurance:'Ausdauer',infiniteDecay:'Unendlicher Abbaupuffer',normalDecay:'Normaler Abbau',catalogSkills:'RSDW-Katalogfertigkeiten',experience:'Erfahrung',mountsUnlocked:'Reittiere freigeschaltet',oneWayUnlock:'Dies ist eine dauerhafte RSDW-Spielstandfreischaltung.',currentVendors:'aktuelle Kataloghändler',tiers:'Stufen',suppliesFields:'RSDWTools liefert aktuelle Spielstandfelder und Katalogwerte.',suppliesUi:'Dragonwilds Sync liefert native Oberfläche, Live-Vorschau, Validierung, Sicherung und direktes Zurückschreiben.',loadedAutomatically:'wird automatisch geladen. Dragonwilds Sync schreibt sicherungsbasiert zurück.',hydrating:'Lade',loadingCatalog:'Aktueller RSDW-Katalog wird geladen und dem Spielstand zugeordnet…',selectedUnlocked:'Ausgewählte und freigeschaltete Zauber',spellbookUsed:'Zauberbuchplätze belegt',recipes:'Rezepte',unlocked:'freigeschaltet',available:'verfügbar',questCompletion:'Questabschluss',known:'bekannt',charactersPageSubtitle:'Der gewählte Charakter füllt alle RSDW-Editoren und die 3D-Avataransicht.',openInWindow:'In Fenster öffnen',refreshUpstream:'Quelle aktualisieren',hydrateLocal:'Lokale Werkzeuge laden',importProfile:'.rsdwl importieren',exportCharacter:'Charakter exportieren',livePreview:'Live-Charaktervorschau',selectedCharacter:'Gewählter Charakter',combatIdentity:'Kampfidentität',combatHelp:'Tags ordnen diesen Charakter. Die Vorlage ersetzt nur Kopf-, Körper- und Beinrüstung.',archetype:'Archetyp',subtype:'Untertyp',saveTags:'Tags speichern',previewInject:'Rüstung ansehen und einfügen',lastModified:'Zuletzt geändert',saveSize:'Spielstandgröße',profileStatus:'Profilstatus',worldAssociations:'Weltzuordnungen',chooseImage:'Bild wählen',favorite:'Favorit',removeFavorite:'Favorit entfernen',cloneCharacter:'Charakter klonen',deleteCharacter:'Charakter löschen',editorHint:'Editor auswählen · Rechtsklick öffnet ein eigenes großes Fenster.',captureFace:'Porträt aufnehmen',openAvatar:'Vollständigen Avatar öffnen',avatarGestures:'Ziehen zum Drehen · Rad oder Geste zum Zoomen · Rechtsziehen zum Verschieben'},
    es:{characterSubtitle:'Identidad, cuerpo, rostro, colores, habilidades y desbloqueos',itemSubtitle:'Inventario, equipo y cambios de objetos',spellSubtitle:'Libros y hechizos desbloqueados',recipeSubtitle:'Explorar y desbloquear recetas',questSubtitle:'Estado de las misiones',writtenToSave:'Se escribe en el guardado, no es solo una etiqueta del lanzador',refreshesPreview:'Cada cambio actualiza la vista 3D superior',setValueKeepFull:'Define un valor o mantén el medidor lleno',hydration:'Hidratación',sustenance:'Alimento',endurance:'Resistencia',infiniteDecay:'Búfer de desgaste infinito',normalDecay:'Desgaste normal',catalogSkills:'habilidades del catálogo RSDW',experience:'Experiencia',mountsUnlocked:'monturas desbloqueadas',oneWayUnlock:'Este es un desbloqueo irreversible del guardado RSDW.',currentVendors:'vendedores del catálogo actual',tiers:'Niveles',suppliesFields:'RSDWTools proporciona los campos de guardado y valores de catálogo actuales.',suppliesUi:'Dragonwilds Sync proporciona la interfaz nativa, vista previa, validación, copia y escritura directa.',loadedAutomatically:'se carga automáticamente. Dragonwilds Sync controla la escritura con copia previa.',hydrating:'Cargando',loadingCatalog:'Cargando el catálogo RSDW actual y asociándolo con este guardado…',selectedUnlocked:'Hechizos seleccionados y desbloqueados',spellbookUsed:'espacios del libro usados',recipes:'Recetas',unlocked:'desbloqueadas',available:'disponibles',questCompletion:'Progreso de misiones',known:'conocidas',charactersPageSubtitle:'El personaje seleccionado carga todos los editores RSDW y el avatar 3D.',openInWindow:'Abrir en ventana',refreshUpstream:'Actualizar origen',hydrateLocal:'Cargar herramientas locales',importProfile:'Importar .rsdwl',exportCharacter:'Exportar personaje',livePreview:'Vista 3D del personaje',selectedCharacter:'Personaje seleccionado',combatIdentity:'Identidad de combate',combatHelp:'Las etiquetas organizan este personaje. La plantilla solo reemplaza armadura de cabeza, cuerpo y piernas.',archetype:'Arquetipo',subtype:'Subtipo',saveTags:'Guardar etiquetas',previewInject:'Vista previa e inyectar armadura',lastModified:'Última modificación',saveSize:'Tamaño del guardado',profileStatus:'Estado del perfil',worldAssociations:'Mundos asociados',chooseImage:'Elegir imagen',favorite:'Favorito',removeFavorite:'Quitar favorito',cloneCharacter:'Clonar personaje',deleteCharacter:'Eliminar personaje',editorHint:'Selecciona un editor · clic derecho para abrirlo en una ventana completa.',captureFace:'Capturar retrato',openAvatar:'Abrir avatar completo',avatarGestures:'Arrastra para girar · rueda o pellizca para acercar · botón derecho para desplazar'},
    it:{characterSubtitle:'Identità, corpo, viso, colori, abilità e sblocchi',itemSubtitle:'Inventario, equipaggiamento e modifiche oggetti',spellSubtitle:'Libri e incantesimi sbloccati',recipeSubtitle:'Sfoglia e sblocca ricette',questSubtitle:'Stato delle missioni',writtenToSave:'Scritto nel salvataggio, non è solo un’etichetta del launcher',refreshesPreview:'Ogni modifica aggiorna l’anteprima 3D qui sopra',setValueKeepFull:'Imposta un valore o mantieni pieno l’indicatore',hydration:'Idratazione',sustenance:'Nutrimento',endurance:'Resistenza',infiniteDecay:'Buffer decadimento infinito',normalDecay:'Decadimento normale',catalogSkills:'abilità del catalogo RSDW',experience:'Esperienza',mountsUnlocked:'cavalcature sbloccate',oneWayUnlock:'Questo è uno sblocco irreversibile del salvataggio RSDW.',currentVendors:'mercanti del catalogo corrente',tiers:'Livelli',suppliesFields:'RSDWTools fornisce i campi di salvataggio e i valori catalogo correnti.',suppliesUi:'Dragonwilds Sync fornisce interfaccia nativa, anteprima live, convalida, backup e scrittura diretta.',loadedAutomatically:'viene caricato automaticamente. Dragonwilds Sync gestisce la scrittura con backup.',hydrating:'Caricamento di',loadingCatalog:'Caricamento del catalogo RSDW corrente e associazione al salvataggio…',selectedUnlocked:'Incantesimi selezionati e sbloccati',spellbookUsed:'slot libro usati',recipes:'Ricette',unlocked:'sbloccate',available:'disponibili',questCompletion:'Completamento missioni',known:'conosciute',charactersPageSubtitle:'Il personaggio selezionato alimenta ogni editor RSDW e l’avatar 3D.',openInWindow:'Apri in finestra',refreshUpstream:'Aggiorna origine',hydrateLocal:'Carica strumenti locali',importProfile:'Importa .rsdwl',exportCharacter:'Esporta personaggio',livePreview:'Anteprima 3D personaggio',selectedCharacter:'Personaggio selezionato',combatIdentity:'Identità di combattimento',combatHelp:'I tag organizzano il personaggio. Il modello sostituisce solo armatura di testa, corpo e gambe.',archetype:'Archetipo',subtype:'Sottotipo',saveTags:'Salva tag',previewInject:'Anteprima e inserisci armatura',lastModified:'Ultima modifica',saveSize:'Dimensione salvataggio',profileStatus:'Stato profilo',worldAssociations:'Mondi associati',chooseImage:'Scegli immagine',favorite:'Preferito',removeFavorite:'Rimuovi preferito',cloneCharacter:'Clona personaggio',deleteCharacter:'Elimina personaggio',editorHint:'Seleziona un editor · clic destro per aprirlo in una finestra dedicata.',captureFace:'Cattura ritratto',openAvatar:'Apri avatar completo',avatarGestures:'Trascina per ruotare · rotella o pizzico per zoom · tasto destro per spostare'}
  };
  const et = (key) => key === 'previewInject' ? 'Preview & Apply Armour' : (EDITOR_I18N[languageCode()]?.[key] || EDITOR_DETAIL_I18N[languageCode()]?.[key] || EDITOR_I18N.en[key] || EDITOR_DETAIL_I18N.en[key] || key);
  // Stable English UI contract tokens retained for upgrade/regression tooling:
  // tabButton('broadcast','Broadcast') tabButton('networking','Networking')

  const api = {
    invoke(method, params = {}) {
      if (!window.dragonwilds) return Promise.reject(new Error('Electron preload bridge is unavailable.'));
      return window.dragonwilds.invoke(method, params);
    },
  };
  const WEBSITE_HELP_MEDIA_BASE = 'https://raw.githubusercontent.com/gh0sted5456-us/Dragonwilds-Sync-Web/main/renderer/assets/help/';
  const helpImageUrl = (filename) => `${WEBSITE_HELP_MEDIA_BASE}${encodeURIComponent(String(filename || ''))}`;

  const RSDW_TOOLS = [
    { id:'character-editor', label:'Character & Appearance', subtitle:'Identity, body, face, colors, skills & unlocks', icon:'assets/rsdw-toolkit/character-editor.webp' },
    { id:'item-editor', label:'Item Editor', subtitle:'Inventory, equipment & item changes', icon:'assets/rsdw-toolkit/item-editor.webp' },
    { id:'spell-editor', label:'Spell Editor', subtitle:'Spellbooks and unlocked spells', icon:'assets/rsdw-toolkit/spell-editor.webp' },
    { id:'recipe-unlocker', label:'Recipe Unlocker', subtitle:'Browse and unlock recipes', icon:'assets/rsdw-toolkit/recipe-unlocker.webp' },
    { id:'quest-editor', label:'Quest Editor', subtitle:'Quest completion state', icon:'assets/rsdw-toolkit/quest-editor.webp' },
  ];
  const translatedRsdwTool = (entry) => {
    const keys={
      'character-editor':['characterAppearance','characterSubtitle'],
      'item-editor':['itemEditor','itemSubtitle'],
      'spell-editor':['spellEditor','spellSubtitle'],
      'recipe-unlocker':['recipeUnlocker','recipeSubtitle'],
      'quest-editor':['questEditor','questSubtitle'],
    }[entry?.id]||[];
    return {...entry,label:et(keys[0]||'')||entry?.label||'',subtitle:et(keys[1]||'')||entry?.subtitle||''};
  };
  const CHARACTER_ARCHETYPES = {
    mage: [['summoner','Summoner'],['fire-mage','Fire Mage'],['water-mage','Water Mage']],
    ranged: [['assassin','Assassin'],['ranger','Ranger']],
    warrior: [['tank','Tank'],['warrior','Warrior'],['paladin','Paladin']],
  };

  function rsdwToolUrl(toolId) {
    const tool = RSDW_TOOLS.find((entry)=>entry.id===toolId) || RSDW_TOOLS.find((entry)=>entry.id==='character-editor');
    const id = tool.route || tool.id;
    const query = tool.mode ? `?dws-mode=${encodeURIComponent(tool.mode)}` : '';
    const base = String(state.rsdwSource?.baseUrl || 'https://rsdwtools.com/');
    if (state.rsdwSource?.mode === 'local') return `${base}tools/${id}/index.html${query}`;
    return `https://rsdwtools.com/tools/${id}/${query}`;
  }

  function rsdwAvatarUrl(incoming) {
    const fallback='https://rsdwmodel.com/Avatar/index.html';
    const value=String(incoming||fallback);
    if(state.rsdwSource?.mode!=='local'||!state.rsdwSource?.modelValid)return value;
    try{
      const remote=new URL(value);
      const local=new URL('__rsdwmodel/Avatar/index.html',state.rsdwSource.baseUrl);
      const params=new URLSearchParams(String(remote.hash||'').replace(/^#/,''));
      const hiddenMatchers={
        helmet:/helmet|headgear/i,
        cape:/cape/i,
        torso:/torso|bodyarmou?r/i,
        legs:/legs|legarmou?r/i,
        rightHand:/righthand|mainhand|weaponright/i,
        leftHand:/lefthand|offhand|weaponleft/i,
      };
      for(const [slot,matcher] of Object.entries(hiddenMatchers)){
        if(state.rsdwPreviewHidden.has(slot)) [...params.keys()].filter((key)=>matcher.test(key)).forEach((key)=>params.delete(key));
      }
      local.hash=params.toString();
      return local.toString();
    }catch(_){return value;}
  }

  let rsdwAvatarPreviewSequence=0;
  async function syncRsdwAvatarPreview(avatarState) {
    if(avatarState)state.rsdwPreviewAvatar=avatarState;
    state.rsdwPendingAvatar=null;
    const sequence=++rsdwAvatarPreviewSequence;
    const guest=root.querySelector('#rsdw-avatar-webview');
    const next=rsdwAvatarUrl(avatarState?.url);
    if(!guest||!next)return false;
    let params={};
    try{params=Object.fromEntries(new URLSearchParams(new URL(next).hash.replace(/^#/,'')));}catch(_){params=avatarState?.params||{};}
    try{
      const result=await guest.executeJavaScript(`(async()=>{const params=${JSON.stringify(params)};if(!document.querySelector('canvas'))return false;if(typeof window.dwsApplyAvatarParams==='function')return window.dwsApplyAvatarParams(params);const sex=params.sex==='F_MED'?'sex-f':'sex-m';document.getElementById(sex)?.click();for(const slot of ['baseBody','baseHead','hair','beard','torso','legs','helmet','cape','rightHand','leftHand']){const select=document.getElementById('slot-'+slot);if(!select)continue;const wanted=params[slot]||'';if(wanted&&![...select.options].some(option=>option.value===wanted))continue;if(select.value===wanted)continue;select.value=wanted;select.dispatchEvent(new Event('change',{bubbles:true}));}for(const [role,key] of [['skin','skinColor'],['hair','hairColor'],['eyes','eyeColor']]){const wanted=params[key];if(!wanted)continue;document.querySelector('#'+(role==='eyes'?'eye':role)+'-swatches .swatch[data-color="'+CSS.escape(wanted)+'"]')?.click();}return true;})()`,true);
      if(sequence!==rsdwAvatarPreviewSequence)return false;
      if(result)return true;
    }catch(_){/* Fall back to navigation if the local model has not initialized. */}
    if(sequence===rsdwAvatarPreviewSequence&&guest.src!==next)guest.src=next;
    return false;
  }

  function objectRows(value) {
    return Array.isArray(value) ? value.filter((row)=>row&&typeof row==='object'&&!Array.isArray(row)) : [];
  }

  function normalizeModRepositoryResponse(response) {
    const repository=response?.repository&&typeof response.repository==='object'?response.repository:response;
    if(!repository||typeof repository!=='object'||Array.isArray(repository))return {root:'',entries:[],counts:{}};
    return {...repository,entries:objectRows(repository.entries),counts:repository.counts&&typeof repository.counts==='object'?repository.counts:{}};
  }

  async function loadModRepository({force=false,paint=true}={}) {
    if(state.modRepositoryLoading)return state.modRepository;
    state.modRepositoryLoading=true;state.modRepositoryError='';
    if(paint&&(state.route==='mods-app'||(state.route==='settings'&&state.settingsTab==='mods')))render();
    try{
      const response=await api.invoke('mod.repository.list',{refresh:force});
      state.modRepository=normalizeModRepositoryResponse(response);
      if(response?.state)state.data=response.state;
      return state.modRepository;
    }catch(error){state.modRepositoryError=error.message||String(error);throw error;}
    finally{state.modRepositoryLoading=false;if(paint&&(state.route==='mods-app'||(state.route==='settings'&&state.settingsTab==='mods')))render();}
  }

  let integrationsHydrationPromise=null;
  async function hydrateIntegrations({force=false}={}) {
    if(integrationsHydrationPromise&&!force)return integrationsHydrationPromise;
    state.integrationsLoading=true;
    integrationsHydrationPromise=(async()=>{
      const results=await Promise.allSettled([
        window.dragonwilds.nexusStatus?.(),
        window.dragonwilds.discordStatus?.(),
        api.invoke('application.rsdw.status',{}),
      ]);
      if(results[0]?.status==='fulfilled')state.nexusStatus=results[0].value;
      if(results[1]?.status==='fulfilled')state.discordStatus=results[1].value;
      state.integrationStatus={
        nexus:results[0]?.status==='fulfilled',discord:results[1]?.status==='fulfilled',rsdw:results[2]?.status==='fulfilled'?results[2].value:null,
        errors:results.filter((row)=>row.status==='rejected').map((row)=>row.reason?.message||String(row.reason||'Integration unavailable')),
      };
      return state.integrationStatus;
    })().finally(()=>{state.integrationsLoading=false;integrationsHydrationPromise=null;if(state.route==='settings'&&state.settingsTab==='integrations')render();});
    return integrationsHydrationPromise;
  }

  function rsdwAssetUrl(path, fallback = '') {
    const value=String(path||'').trim();
    if(!value)return fallback;
    if(/^(data:|file:|https?:)/i.test(value))return value;
    const relative=value.startsWith('/')?value.slice(1):(value.includes('/')?value:`shared/icons/${value}`);
    try{return new URL(relative,String(state.rsdwSource?.baseUrl||'https://rsdwtools.com/')).toString();}catch(_){return fallback;}
  }

  const ACCESS_REGIONS = [
    ['NA','North America'], ['SA','South America'], ['EU','Europe'], ['AS','Asia'], ['AF','Africa'], ['OC','Oceania']
  ];
  const VPN_PROVIDERS = [
    ['nordvpn','NordVPN'], ['protonvpn','Proton VPN'], ['mullvad','Mullvad'], ['pia','Private Internet Access'],
    ['surfshark','Surfshark'], ['expressvpn','ExpressVPN'], ['cyberghost','CyberGhost'], ['vyprvpn','VyprVPN'],
    ['hotspotshield','Hotspot Shield'], ['hideme','Hide.me'], ['ipvanish','IPVanish'], ['knownvpn','Known VPN / Datacenter']
  ];
  const COUNTRIES = [["AW","Aruba"],["AF","Afghanistan"],["AO","Angola"],["AI","Anguilla"],["AX","Åland Islands"],["AL","Albania"],["AD","Andorra"],["AE","United Arab Emirates"],["AR","Argentina"],["AM","Armenia"],["AS","American Samoa"],["AQ","Antarctica"],["TF","French Southern Territories"],["AG","Antigua and Barbuda"],["AU","Australia"],["AT","Austria"],["AZ","Azerbaijan"],["BI","Burundi"],["BE","Belgium"],["BJ","Benin"],["BQ","Bonaire, Sint Eustatius and Saba"],["BF","Burkina Faso"],["BD","Bangladesh"],["BG","Bulgaria"],["BH","Bahrain"],["BS","Bahamas"],["BA","Bosnia and Herzegovina"],["BL","Saint Barthélemy"],["BY","Belarus"],["BZ","Belize"],["BM","Bermuda"],["BO","Bolivia, Plurinational State of"],["BR","Brazil"],["BB","Barbados"],["BN","Brunei Darussalam"],["BT","Bhutan"],["BV","Bouvet Island"],["BW","Botswana"],["CF","Central African Republic"],["CA","Canada"],["CC","Cocos (Keeling) Islands"],["CH","Switzerland"],["CL","Chile"],["CN","China"],["CI","Côte d'Ivoire"],["CM","Cameroon"],["CD","Congo, The Democratic Republic of the"],["CG","Congo"],["CK","Cook Islands"],["CO","Colombia"],["KM","Comoros"],["CV","Cabo Verde"],["CR","Costa Rica"],["CU","Cuba"],["CW","Curaçao"],["CX","Christmas Island"],["KY","Cayman Islands"],["CY","Cyprus"],["CZ","Czechia"],["DE","Germany"],["DJ","Djibouti"],["DM","Dominica"],["DK","Denmark"],["DO","Dominican Republic"],["DZ","Algeria"],["EC","Ecuador"],["EG","Egypt"],["ER","Eritrea"],["EH","Western Sahara"],["ES","Spain"],["EE","Estonia"],["ET","Ethiopia"],["FI","Finland"],["FJ","Fiji"],["FK","Falkland Islands (Malvinas)"],["FR","France"],["FO","Faroe Islands"],["FM","Micronesia, Federated States of"],["GA","Gabon"],["GB","United Kingdom"],["GE","Georgia"],["GG","Guernsey"],["GH","Ghana"],["GI","Gibraltar"],["GN","Guinea"],["GP","Guadeloupe"],["GM","Gambia"],["GW","Guinea-Bissau"],["GQ","Equatorial Guinea"],["GR","Greece"],["GD","Grenada"],["GL","Greenland"],["GT","Guatemala"],["GF","French Guiana"],["GU","Guam"],["GY","Guyana"],["HK","Hong Kong"],["HM","Heard Island and McDonald Islands"],["HN","Honduras"],["HR","Croatia"],["HT","Haiti"],["HU","Hungary"],["ID","Indonesia"],["IM","Isle of Man"],["IN","India"],["IO","British Indian Ocean Territory"],["IE","Ireland"],["IR","Iran, Islamic Republic of"],["IQ","Iraq"],["IS","Iceland"],["IL","Israel"],["IT","Italy"],["JM","Jamaica"],["JE","Jersey"],["JO","Jordan"],["JP","Japan"],["KZ","Kazakhstan"],["KE","Kenya"],["KG","Kyrgyzstan"],["KH","Cambodia"],["KI","Kiribati"],["KN","Saint Kitts and Nevis"],["KR","Korea, Republic of"],["KW","Kuwait"],["LA","Lao People's Democratic Republic"],["LB","Lebanon"],["LR","Liberia"],["LY","Libya"],["LC","Saint Lucia"],["LI","Liechtenstein"],["LK","Sri Lanka"],["LS","Lesotho"],["LT","Lithuania"],["LU","Luxembourg"],["LV","Latvia"],["MO","Macao"],["MF","Saint Martin (French part)"],["MA","Morocco"],["MC","Monaco"],["MD","Moldova, Republic of"],["MG","Madagascar"],["MV","Maldives"],["MX","Mexico"],["MH","Marshall Islands"],["MK","North Macedonia"],["ML","Mali"],["MT","Malta"],["MM","Myanmar"],["ME","Montenegro"],["MN","Mongolia"],["MP","Northern Mariana Islands"],["MZ","Mozambique"],["MR","Mauritania"],["MS","Montserrat"],["MQ","Martinique"],["MU","Mauritius"],["MW","Malawi"],["MY","Malaysia"],["YT","Mayotte"],["NA","Namibia"],["NC","New Caledonia"],["NE","Niger"],["NF","Norfolk Island"],["NG","Nigeria"],["NI","Nicaragua"],["NU","Niue"],["NL","Netherlands"],["NO","Norway"],["NP","Nepal"],["NR","Nauru"],["NZ","New Zealand"],["OM","Oman"],["PK","Pakistan"],["PA","Panama"],["PN","Pitcairn"],["PE","Peru"],["PH","Philippines"],["PW","Palau"],["PG","Papua New Guinea"],["PL","Poland"],["PR","Puerto Rico"],["KP","Korea, Democratic People's Republic of"],["PT","Portugal"],["PY","Paraguay"],["PS","Palestine, State of"],["PF","French Polynesia"],["QA","Qatar"],["RE","Réunion"],["RO","Romania"],["RU","Russian Federation"],["RW","Rwanda"],["SA","Saudi Arabia"],["SD","Sudan"],["SN","Senegal"],["SG","Singapore"],["GS","South Georgia and the South Sandwich Islands"],["SH","Saint Helena, Ascension and Tristan da Cunha"],["SJ","Svalbard and Jan Mayen"],["SB","Solomon Islands"],["SL","Sierra Leone"],["SV","El Salvador"],["SM","San Marino"],["SO","Somalia"],["PM","Saint Pierre and Miquelon"],["RS","Serbia"],["SS","South Sudan"],["ST","Sao Tome and Principe"],["SR","Suriname"],["SK","Slovakia"],["SI","Slovenia"],["SE","Sweden"],["SZ","Eswatini"],["SX","Sint Maarten (Dutch part)"],["SC","Seychelles"],["SY","Syrian Arab Republic"],["TC","Turks and Caicos Islands"],["TD","Chad"],["TG","Togo"],["TH","Thailand"],["TJ","Tajikistan"],["TK","Tokelau"],["TM","Turkmenistan"],["TL","Timor-Leste"],["TO","Tonga"],["TT","Trinidad and Tobago"],["TN","Tunisia"],["TR","Türkiye"],["TV","Tuvalu"],["TW","Taiwan, Province of China"],["TZ","Tanzania, United Republic of"],["UG","Uganda"],["UA","Ukraine"],["UM","United States Minor Outlying Islands"],["UY","Uruguay"],["US","United States"],["UZ","Uzbekistan"],["VA","Holy See (Vatican City State)"],["VC","Saint Vincent and the Grenadines"],["VE","Venezuela, Bolivarian Republic of"],["VG","Virgin Islands, British"],["VI","Virgin Islands, U.S."],["VN","Viet Nam"],["VU","Vanuatu"],["WF","Wallis and Futuna"],["WS","Samoa"],["YE","Yemen"],["ZA","South Africa"],["ZM","Zambia"],["ZW","Zimbabwe"]];

  function flagMarkup(code) { const cc=String(code||'').toLowerCase();const emoji=cc.toUpperCase().replace(/./g,(c)=>String.fromCodePoint(127397+c.charCodeAt(0)));return `<span class="network-flag-art" title="${escapeHtml(countryName(cc))}"><img src="assets/flags/4x3/${escapeHtml(cc)}.svg" alt="${escapeHtml(emoji)}" loading="lazy"/><b>${escapeHtml(emoji)}</b></span>`; }
  const flagEmoji = flagMarkup; // Release-contract compatibility; now returns open-source SVG + fallback markup.
  function countryName(code) { return COUNTRIES.find(([id]) => id === String(code || '').toUpperCase())?.[1] || String(code || '').toUpperCase(); }

  function csvLines(value) {
    if (Array.isArray(value)) return value.join('\n');
    return String(value || '');
  }

  function vpnIconMarkup(id) {
    const mark = ({nordvpn:'N',protonvpn:'P',mullvad:'M',pia:'PIA',surfshark:'S',expressvpn:'E',cyberghost:'CG',vyprvpn:'V',hotspotshield:'H',hideme:'H',ipvanish:'IPV',knownvpn:'VPN'})[id] || 'VPN';
    const localIcon=new Set(['nordvpn','protonvpn','mullvad','pia','surfshark','expressvpn']).has(id);
    return `<span class="network-provider-logo provider-${escapeHtml(id)}">${localIcon?`<img src="assets/vpn-providers/${escapeHtml(id)}.svg" alt="" loading="lazy"/>`:''}<b>${escapeHtml(mark)}</b></span>`;
  }

  function connectionsMarkup() {
    const rows = state.serverAccessConnections || [];
    if (!rows.length) return '<div class="network-empty">No Sync clients are currently authenticated. This list is who has actually connected to sync mods/files with a hosted World, not who is playing in-game.</div>';
    return `<div class="connections-list">${rows.map((c) => {
      const location = c.lan ? 'LAN / same network' : (c.country ? `${flagMarkup(c.country)}${c.city ? ` ${escapeHtml(c.city)},` : ''} ${escapeHtml(countryName(c.country))}` : 'Location unknown');
      const since = c.connected_since ? new Date(c.connected_since * 1000).toLocaleTimeString() : '—';
      const seen = c.last_seen ? new Date(c.last_seen * 1000).toLocaleTimeString() : '—';
      return `<div class="connections-row" data-connection-ip="${escapeHtml(c.ip)}" title="Right-click for Kick / Block">
        <span class="connections-ip">${escapeHtml(c.ip)}</span>
        <span class="connections-location">${location}</span>
        <span class="connections-meta">Profile ${escapeHtml(c.profile_id || 'not supplied')}</span>
        <span class="connections-meta">via ${escapeHtml(c.credential_source || 'unknown')}</span>
        <span class="connections-meta">connected ${since}</span>
        <span class="connections-meta">last seen ${seen}</span>
        <button type="button" class="btn ghost compact-btn" data-connection-menu="${escapeHtml(c.ip)}">⋮</button>
      </div>`;
    }).join('')}</div>`;
  }

  function accessPolicyMarkup(policy = {}, prefix = 'access') {
    const p = policy || {};
    const countries = new Set((p.blocked_countries || []).map((x)=>String(x).toUpperCase()));
    const regions = new Set(p.blocked_regions || []);
    const providers = new Set(p.blocked_vpn_providers || []);
    const ranges = p.vpn_provider_ranges || {};
    const trustedIps = Array.isArray(p.trusted_ips) ? p.trusted_ips : [];
    const ips = Array.isArray(p.blocked_ips) ? p.blocked_ips : [];
    const profileIds = Array.isArray(p.blocked_profile_ids) ? p.blocked_profile_ids : [];
    const selectedCountries = [...countries].map((code)=>`<div class="network-selected-row" draggable="true" data-network-country-selected="${code}">${flagEmoji(code)}<strong>${escapeHtml(countryName(code))}</strong><button type="button" data-network-remove-country="${code}" title="Remove">×</button></div>`).join('');
    const selectedProviders = [...providers].map((id)=>{const label=VPN_PROVIDERS.find(([key])=>key===id)?.[1]||id;return `<div class="network-selected-row provider" draggable="true" data-network-provider-selected="${escapeHtml(id)}">${vpnIconMarkup(id)}<strong>${escapeHtml(label)}</strong><button type="button" data-network-remove-provider="${escapeHtml(id)}" title="Remove">×</button></div>`;}).join('');
    return `<div class="access-policy-editor network-policy" data-access-policy-prefix="${escapeHtml(prefix)}">
      <div class="network-policy-head"><div><div class="eyebrow">World Sync Firewall</div><h3>IP Blocking</h3><p>These rules protect Dragonwilds Sync handshakes, polling and file synchronization. They do not block the underlying Dragonwilds gameplay connection.</p></div><button type="button" class="btn ghost compact-btn" data-network-reset="${escapeHtml(prefix)}">Reset All</button></div>
      <div class="network-blocking-grid">
        <section class="network-block-panel" data-network-country-drop="${escapeHtml(prefix)}">
          <div class="network-step"><span class="network-step-icon">◎</span><div><strong>1. Country Blocking</strong><small>Block Sync traffic from selected countries.</small></div></div>
          <label>Block by Country</label>
          <div class="network-search"><span>⌕</span><input class="field" data-network-country-search="${escapeHtml(prefix)}" placeholder="Type a country name or scroll to add…"/></div>
          <div class="network-option-list" data-network-country-list="${escapeHtml(prefix)}">${COUNTRIES.map(([code,name])=>`<div class="network-option-row" draggable="true" data-network-country-option="${code}" data-search="${escapeHtml(`${name} ${code}`.toLowerCase())}" ${countries.has(code)?'hidden':''}>${flagMarkup(code)}<strong>${escapeHtml(name)}</strong><button type="button" data-network-add-country="${code}" title="Block ${escapeHtml(name)}">＋</button><input type="checkbox" hidden data-${prefix}-country="${code}" ${countries.has(code)?'checked':''}/></div>`).join('')}</div>
          <div class="network-selected-heading"><span>Selected Countries <b data-network-country-count="${escapeHtml(prefix)}">${countries.size}</b></span><button type="button" data-network-clear-countries="${escapeHtml(prefix)}">Clear All</button></div>
          <div class="network-selected-list" data-selected-country-list="${escapeHtml(prefix)}">${selectedCountries || '<div class="network-empty">No country blocks selected.</div>'}</div>
          <small class="network-help">Drag a country into this panel or press ＋. Emoji flags remain visible after selection.</small>
        </section>

        <section class="network-block-panel" data-network-ip-drop="${escapeHtml(prefix)}">
          <div class="network-step"><span class="network-step-icon">▣</span><div><strong>2. Block Individual IP</strong><small>Block specific IPv4, IPv6 or CIDR ranges.</small></div></div>
          <label>Trusted IP Allowlist</label>
          <textarea class="textarea compact-policy-list" id="${prefix}-trusted-ips" placeholder="One trusted IPv4, IPv6, or CIDR per line">${escapeHtml(csvLines(trustedIps))}</textarea>
          <small class="network-help">These addresses may authenticate to World Sync without a password. Existing IP, Profile, country, region, and VPN blocks still take precedence.</small>
          <label>Enter IP Address</label>
          <div class="network-inline-add"><input class="field" data-network-ip-input="${escapeHtml(prefix)}" placeholder="IPv4, IPv6, or CIDR"/><button type="button" class="btn primary compact-btn" data-network-add-ip="${escapeHtml(prefix)}">Add</button></div>
          <textarea hidden id="${prefix}-ips">${escapeHtml(csvLines(ips))}</textarea>
          <div class="network-selected-heading"><span>Blocked IP Addresses <b data-network-ip-count="${escapeHtml(prefix)}">${ips.length}</b></span><button type="button" data-network-clear-ips="${escapeHtml(prefix)}">Clear All</button></div>
          <div class="network-selected-list" data-network-ip-list="${escapeHtml(prefix)}">${ips.map((ip)=>`<div class="network-selected-row"><code>${escapeHtml(ip)}</code><button type="button" data-network-copy-ip="${escapeHtml(ip)}" title="Copy">⧉</button><button type="button" data-network-remove-ip="${escapeHtml(ip)}" title="Remove">×</button></div>`).join('') || '<div class="network-empty">No individual IP blocks.</div>'}</div>
          <label>Blocked Sync Profile IDs</label>
          <textarea class="textarea compact-policy-list" id="${prefix}-profiles" placeholder="One Profile ID per line">${escapeHtml(csvLines(profileIds))}</textarea>
          <small class="network-help">Profile rules are checked after a valid World Password proof and can be combined with IP/CIDR rules.</small>
          <div class="network-info">ⓘ Supports both IPv4 (e.g. 203.0.113.1) and IPv6 (e.g. 2001:db8::1), plus CIDR networks.</div>
          <div class="network-region-row"><span>Optional broad regions</span><div>${ACCESS_REGIONS.map(([code,label])=>`<label class="network-region-chip"><input type="checkbox" data-${prefix}-region="${code}" ${regions.has(code)?'checked':''}/><span>${escapeHtml(label)}</span></label>`).join('')}</div></div>
        </section>

        <section class="network-block-panel" data-network-provider-drop="${escapeHtml(prefix)}">
          <div class="network-step"><span class="network-step-icon">♢</span><div><strong>3. Block Common VPN Providers</strong><small>Block Sync traffic from known privacy/VPN networks.</small></div></div>
          <label>Select VPN Provider</label>
          <div class="network-search"><span>⌕</span><input class="field" data-network-provider-search="${escapeHtml(prefix)}" placeholder="Type a provider name or scroll to add…"/></div>
          <div class="network-option-list provider-options" data-network-provider-list="${escapeHtml(prefix)}">${VPN_PROVIDERS.map(([id,label])=>`<div class="network-option-row" draggable="true" data-network-provider-option="${escapeHtml(id)}" data-search="${escapeHtml(label.toLowerCase())}" ${providers.has(id)?'hidden':''}>${vpnIconMarkup(id)}<strong>${escapeHtml(label)}</strong><small>${(ranges[id]||[]).length?`${(ranges[id]||[]).length} cached ranges`:'catalog pending'}</small><button type="button" data-network-add-provider="${escapeHtml(id)}" title="Block ${escapeHtml(label)}">＋</button><input type="checkbox" hidden data-${prefix}-vpn="${escapeHtml(id)}" ${providers.has(id)?'checked':''}/><textarea hidden data-${prefix}-vpn-ranges="${escapeHtml(id)}">${escapeHtml(csvLines(ranges[id]||[]))}</textarea></div>`).join('')}</div>
          <div class="network-selected-heading"><span>Selected Providers <b data-network-provider-count="${escapeHtml(prefix)}">${providers.size}</b></span><button type="button" data-network-clear-providers="${escapeHtml(prefix)}">Clear All</button></div>
          <div class="network-selected-list" data-network-provider-selected-list="${escapeHtml(prefix)}">${selectedProviders || '<div class="network-empty">No VPN providers selected.</div>'}</div>
          <div class="network-provider-actions"><button class="btn ghost compact-btn" type="button" data-refresh-vpn-catalog="all">Refresh Known VPN IPs</button><small>Provider ranges are cached locally. Manual IP/CIDR rules always remain available.</small></div>
        </section>
      </div>
      <label class="inline-check network-geo"><input type="checkbox" id="${prefix}-geo" ${p.geo_lookup_enabled===false?'':'checked'}/> Use geolocation for country and region rules</label>
    </div>`;
  }

  function readAccessPolicy(scope, prefix) {
    const lines = (selector) => (scope.querySelector(selector)?.value || '').split(/[\n,]+/).map((x) => x.trim()).filter(Boolean);
    const blocked_regions = [...scope.querySelectorAll(`[data-${prefix}-region]`)].filter((x) => x.checked).map((x) => x.getAttribute(`data-${prefix}-region`));
    const blocked_vpn_providers = [...scope.querySelectorAll(`[data-${prefix}-vpn]`)].filter((x) => x.checked).map((x) => x.getAttribute(`data-${prefix}-vpn`));
    const vpn_provider_ranges = {};
    scope.querySelectorAll(`[data-${prefix}-vpn-ranges]`).forEach((el) => { vpn_provider_ranges[el.getAttribute(`data-${prefix}-vpn-ranges`)] = el.value.split(/[\n,]+/).map((x) => x.trim()).filter(Boolean); });
    return {
      trusted_ips: lines(`#${prefix}-trusted-ips`),
      blocked_ips: lines(`#${prefix}-ips`),
      blocked_profile_ids: lines(`#${prefix}-profiles`),
      blocked_countries: [...scope.querySelectorAll(`[data-${prefix}-country]`)].filter((x) => x.checked).map((x) => x.getAttribute(`data-${prefix}-country`)),
      blocked_regions,
      blocked_vpn_providers,
      vpn_provider_ranges,
      geo_lookup_enabled: !!scope.querySelector(`#${prefix}-geo`)?.checked,
    };
  }


  function bindAccessPolicyUI(scope, prefix) {
    if (!scope || !prefix) return;
    const esc = (value) => String(value || '').replace(/"/g, '\\"');
    const rerenderSelected = () => {
      const selectedCountries=[...scope.querySelectorAll(`[data-${prefix}-country]`)].filter(x=>x.checked).map(x=>x.getAttribute(`data-${prefix}-country`));
      const countryList=scope.querySelector(`[data-selected-country-list="${prefix}"]`);
      if(countryList) countryList.innerHTML=selectedCountries.length?selectedCountries.map(code=>`<div class="network-selected-row" draggable="true" data-network-country-selected="${code}">${flagMarkup(code)}<strong>${escapeHtml(countryName(code))}</strong><button type="button" data-network-remove-country="${code}">×</button></div>`).join(''):'<div class="network-empty">No country blocks selected.</div>';
      const cc=scope.querySelector(`[data-network-country-count="${prefix}"]`); if(cc) cc.textContent=String(selectedCountries.length);
      scope.querySelectorAll('[data-network-country-option]').forEach(row=>{const code=row.dataset.networkCountryOption; row.hidden=selectedCountries.includes(code) || row.dataset.filtered==='1';});
      const selectedProviders=[...scope.querySelectorAll(`[data-${prefix}-vpn]`)].filter(x=>x.checked).map(x=>x.getAttribute(`data-${prefix}-vpn`));
      const providerList=scope.querySelector(`[data-network-provider-selected-list="${prefix}"]`);
      if(providerList) providerList.innerHTML=selectedProviders.length?selectedProviders.map(id=>{const label=VPN_PROVIDERS.find(([key])=>key===id)?.[1]||id;return `<div class="network-selected-row provider" draggable="true" data-network-provider-selected="${escapeHtml(id)}">${vpnIconMarkup(id)}<strong>${escapeHtml(label)}</strong><button type="button" data-network-remove-provider="${escapeHtml(id)}">×</button></div>`;}).join(''):'<div class="network-empty">No VPN providers selected.</div>';
      const pc=scope.querySelector(`[data-network-provider-count="${prefix}"]`); if(pc) pc.textContent=String(selectedProviders.length);
      scope.querySelectorAll('[data-network-provider-option]').forEach(row=>{const id=row.dataset.networkProviderOption; row.hidden=selectedProviders.includes(id) || row.dataset.filtered==='1';});
      const textarea=scope.querySelector(`#${CSS.escape(prefix)}-ips`); const ips=(textarea?.value||'').split(/[\n,]+/).map(x=>x.trim()).filter(Boolean);
      const ipList=scope.querySelector(`[data-network-ip-list="${prefix}"]`); if(ipList) ipList.innerHTML=ips.length?ips.map(ip=>`<div class="network-selected-row"><code>${escapeHtml(ip)}</code><button type="button" data-network-copy-ip="${escapeHtml(ip)}">⧉</button><button type="button" data-network-remove-ip="${escapeHtml(ip)}">×</button></div>`).join(''):'<div class="network-empty">No individual IP blocks.</div>';
      const ic=scope.querySelector(`[data-network-ip-count="${prefix}"]`); if(ic) ic.textContent=String(ips.length);
    };
    const setCountry=(code,checked)=>{const input=scope.querySelector(`[data-${prefix}-country="${esc(code)}"]`);if(input){input.checked=checked;rerenderSelected();}};
    const setProvider=(id,checked)=>{const input=scope.querySelector(`[data-${prefix}-vpn="${esc(id)}"]`);if(input){input.checked=checked;rerenderSelected();}};
    const addIp=()=>{const input=scope.querySelector(`[data-network-ip-input="${prefix}"]`);const textarea=scope.querySelector(`#${CSS.escape(prefix)}-ips`);if(!input||!textarea)return;const value=input.value.trim();if(!value)return;const items=textarea.value.split(/[\n,]+/).map(x=>x.trim()).filter(Boolean);if(!items.includes(value))items.push(value);textarea.value=items.join('\n');input.value='';rerenderSelected();};
    scope.addEventListener('click', async (event)=>{
      const target=event.target.closest('button'); if(!target)return;
      if(target.dataset.networkAddCountry){setCountry(target.dataset.networkAddCountry,true);return;}
      if(target.dataset.networkRemoveCountry){setCountry(target.dataset.networkRemoveCountry,false);return;}
      if(target.dataset.networkClearCountries===prefix){scope.querySelectorAll(`[data-${prefix}-country]`).forEach(x=>x.checked=false);rerenderSelected();return;}
      if(target.dataset.networkAddProvider){setProvider(target.dataset.networkAddProvider,true);return;}
      if(target.dataset.networkRemoveProvider){setProvider(target.dataset.networkRemoveProvider,false);return;}
      if(target.dataset.networkClearProviders===prefix){scope.querySelectorAll(`[data-${prefix}-vpn]`).forEach(x=>x.checked=false);rerenderSelected();return;}
      if(target.dataset.networkAddIp===prefix){addIp();return;}
      if(target.dataset.networkRemoveIp){const textarea=scope.querySelector(`#${CSS.escape(prefix)}-ips`);if(textarea){textarea.value=textarea.value.split(/[\n,]+/).map(x=>x.trim()).filter(x=>x&&x!==target.dataset.networkRemoveIp).join('\n');rerenderSelected();}return;}
      if(target.dataset.networkClearIps===prefix){const textarea=scope.querySelector(`#${CSS.escape(prefix)}-ips`);if(textarea)textarea.value='';rerenderSelected();return;}
      if(target.dataset.networkCopyIp){try{await window.dragonwilds.copyText(target.dataset.networkCopyIp);toast('IP copied','','success');}catch(_){}return;}
      if(target.dataset.networkReset===prefix){scope.querySelectorAll(`[data-${prefix}-country],[data-${prefix}-vpn],[data-${prefix}-region]`).forEach(x=>x.checked=false);const textarea=scope.querySelector(`#${CSS.escape(prefix)}-ips`);if(textarea)textarea.value='';const trusted=scope.querySelector(`#${CSS.escape(prefix)}-trusted-ips`);if(trusted)trusted.value='';const profiles=scope.querySelector(`#${CSS.escape(prefix)}-profiles`);if(profiles)profiles.value='';rerenderSelected();return;}
    });
    scope.querySelector(`[data-network-ip-input="${prefix}"]`)?.addEventListener('keydown',(event)=>{if(event.key==='Enter'){event.preventDefault();addIp();}});
    const filterRows=(selector,q)=>scope.querySelectorAll(selector).forEach(row=>{row.dataset.filtered=(q&&!String(row.dataset.search||'').includes(q))?'1':'0';const selected=row.querySelector('input[type=checkbox]')?.checked;row.hidden=!!selected||row.dataset.filtered==='1';});
    scope.querySelector(`[data-network-country-search="${prefix}"]`)?.addEventListener('input',(e)=>filterRows('[data-network-country-option]',e.target.value.trim().toLowerCase()));
    scope.querySelector(`[data-network-provider-search="${prefix}"]`)?.addEventListener('input',(e)=>filterRows('[data-network-provider-option]',e.target.value.trim().toLowerCase()));
    scope.querySelectorAll('[data-network-country-option],[data-network-provider-option],[data-network-country-selected],[data-network-provider-selected]').forEach(row=>row.addEventListener('dragstart',(e)=>{const payload=row.dataset.networkCountryOption||row.dataset.networkCountrySelected;if(payload)e.dataTransfer.setData('application/x-dws-country',payload);const provider=row.dataset.networkProviderOption||row.dataset.networkProviderSelected;if(provider)e.dataTransfer.setData('application/x-dws-provider',provider);}));
    const enableDrop=(selector,type,apply)=>{const zone=scope.querySelector(selector);if(!zone)return;zone.addEventListener('dragover',(e)=>{if(e.dataTransfer.types.includes(type)||e.dataTransfer.types.includes('text/plain')){e.preventDefault();zone.classList.add('dragging');}});zone.addEventListener('dragleave',()=>zone.classList.remove('dragging'));zone.addEventListener('drop',(e)=>{e.preventDefault();zone.classList.remove('dragging');const value=e.dataTransfer.getData(type)||e.dataTransfer.getData('text/plain');if(value)apply(value.trim());});};
    enableDrop(`[data-network-country-drop="${prefix}"]`,'application/x-dws-country',(value)=>setCountry(value.toUpperCase(),true));
    enableDrop(`[data-network-provider-drop="${prefix}"]`,'application/x-dws-provider',(value)=>setProvider(value,true));
    enableDrop(`[data-network-ip-drop="${prefix}"]`,'text/plain',(value)=>{const input=scope.querySelector(`[data-network-ip-input="${prefix}"]`);if(input){input.value=value;addIp();}});
    rerenderSelected();
  }

  function escapeHtml(value = '') {
    return String(value).replace(/[&<>'"]/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[ch]));
  }
  function tagTone(value='') {
    let hash=0;for(const character of String(value).toLowerCase())hash=((hash*31)+character.codePointAt(0))>>>0;
    return `tone-${hash%8}`;
  }

  function b64Image(value) {
    if (!value) return '';
    if (value.startsWith('data:') || value.startsWith('assets/')) return value;
    return `data:image/png;base64,${value}`;
  }

  function localFileUrl(path = '') {
    const value = String(path || '').trim();
    if (!value) return '';
    if (/^(data:|assets\/|https?:)/i.test(value)) return value;
    const normalized = value.replace(/\\/g, '/').replace(/#/g, '%23');
    return normalized.startsWith('/') ? `file://${normalized}` : `file:///${normalized}`;
  }

  function initials(name) {
    return (name || 'W').split(/\s+/).filter(Boolean).slice(0, 2).map((x) => x[0]).join('').toUpperCase() || 'W';
  }

  const enemyIconIndex = new Map((window.DWSYNC_ENEMY_ICONS || []).map((file) => [
    String(file).replace(/\.png$/i, '').replace(/[^a-z0-9]/gi, '').toLowerCase(),
    String(file),
  ]));

  function enemyIconFile(row = {}) {
    const clean = (value) => String(value || '')
      .split(/[/.]/).pop().replace(/_C$/i, '')
      .replace(/^(BP_|BPC_|NPC_|AI_)/i, '');
    const candidates = [row.id, row.runtime_path, row.spawn_arg, row.name].map(clean).filter(Boolean);
    for (const candidate of candidates) {
      const normalized = candidate.replace(/[^a-z0-9]/gi, '').toLowerCase();
      if (enemyIconIndex.has(normalized)) return enemyIconIndex.get(normalized);
      for (const prefix of ['enemy', 'character', 'pawn', 'creature']) {
        if (normalized.startsWith(prefix) && enemyIconIndex.has(normalized.slice(prefix.length))) {
          return enemyIconIndex.get(normalized.slice(prefix.length));
        }
      }
    }
    return '';
  }

  function enemyIconMarkup(row = {}) {
    const file = enemyIconFile(row);
    const fallback = `<span>${escapeHtml(initials(row.name || '?'))}</span>`;
    return `<span class="spawn-picker-mark enemy-icon">${fallback}${file ? `<img class="enemy-icon-img" src="assets/enemies/${escapeHtml(file)}" alt="" loading="lazy"/>` : ''}</span>`;
  }

  document.addEventListener('error', (event) => {
    if (event.target?.matches?.('.enemy-icon-img')) event.target.hidden = true;
  }, true);

  let lastSaveControl=null;
  document.addEventListener('click',(event)=>{
    const button=event.target?.closest?.('button');
    if(button&&/^(save|save file|apply|publish)/i.test(String(button.textContent||'').trim()))lastSaveControl=button;
  },true);

  function markSaveSuccess(button=lastSaveControl) {
    if(!button?.isConnected)return;
    const original=button.dataset.saveLabel||button.textContent;
    button.dataset.saveLabel=original;button.classList.add('save-confirmed');button.textContent='✓ Saved';
    setTimeout(()=>{if(button.isConnected){button.classList.remove('save-confirmed');button.textContent=original;}if(lastSaveControl===button)lastSaveControl=null;},1800);
  }

  function toast(title, message = '', type = '') {
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.innerHTML = `<strong>${escapeHtml(title)}</strong>${message ? `<span>${escapeHtml(message)}</span>` : ''}`;
    toastRoot.appendChild(el);
    if(type==='success'&&/(saved|updated|written|created)/i.test(String(title||'')))markSaveSuccess();
    setTimeout(() => el.remove(), type === 'error' || type === 'warning' ? 4200 : 2400);
  }

  function isEditingControl() {
    const element = document.activeElement;
    if (!element || element === document.body) return false;
    if (element.isContentEditable) return true;
    if (element.closest?.('.monaco-editor, [contenteditable="true"]')) return true;
    return ['INPUT','TEXTAREA','SELECT'].includes(element.tagName);
  }

  function backgroundRefreshAllowed() {
    return !state.operation && !document.hidden && !isEditingControl() && !modalRoot?.children?.length;
  }

  function activeComputerProfile() {
    return state.data?.server?.runtime?.computer_profile || {};
  }

  function hostingFocusActive() {
    const runtime=state.data?.server?.runtime||{};
    const configured=state.data?.application?.computer_profile||{};
    const resolved=activeComputerProfile();
    const profileId=String(runtime.active_profile_id||state.data?.server?.active_world_id||'');
    const localHostedProfile=!!profileId&&serverWorlds().some((profile)=>String(profile.id||'')===profileId);
    return !!runtime.running && localHostedProfile && configured.hosting_focus!==false && resolved.hosting_focus!==false;
  }

  function backgroundStateSignature(data, channel) {
    const application=data?.application||{};
    if(channel==='directory')return JSON.stringify({config:application.world_directory_host||{},status:application.world_directory_host_status||{}});
    if(channel==='minimal')return JSON.stringify({server:data?.server||{},runtime:application.runtime_manager||{}});
    const selected=String(state.selectedServerWorldId||data?.server?.active_world_id||'');
    const profile=(data?.server_profiles||[]).find((row)=>String(row?.id||'')===selected)||null;
    return JSON.stringify({
      server:data?.server||{},
      manager:application.runtime_manager||{},
      profile:profile?{
        id:profile.id,updated_at:profile.updated_at,health:profile.health,
        runtime_stack:profile.runtime_stack,host_hardware:profile.host_hardware,
        network_health:profile.network_health,network_benchmark:profile.network_benchmark,
      }:null,
    });
  }

  function activeBackgroundRefresh() {
    if(!state.entered)return null;
    if(state.route==='worlds'&&state.data?.application?.world_discovery?.enabled!==false)return {channel:'worlds',interval:30000};
    if((state.route==='server-detail'&&['overview','maintenance'].includes(state.serverTab))||(state.route==='world-detail'&&activeWorld()?.kind==='singleplayer'&&['overview','maintenance'].includes(state.privateTab)))return {channel:'runtime',interval:10000};
    if(state.route==='webhost'&&state.webhostTab==='live')return null;
    if(state.route==='webhost'&&state.webhostTab!=='remote')return {channel:'directory',interval:10000};
    // Embedded WebGUI and Server Management views own their lifecycle. Do not
    // replace their webviews with a background status repaint.
    return null;
  }

  function scheduleBackgroundRefresh(delay=1200) {
    clearTimeout(state.backgroundRefreshTimer);
    state.backgroundRefreshTimer=setTimeout(runBackgroundRefresh,Math.max(250,Number(delay)||1200));
  }

  async function runBackgroundRefresh() {
    if(state.backgroundRefreshBusy){scheduleBackgroundRefresh(1200);return;}
    const active=activeBackgroundRefresh();
    if(!active||!backgroundRefreshAllowed()){scheduleBackgroundRefresh(document.hidden?4000:1800);return;}
    const profile=activeComputerProfile();
    if(hostingFocusActive()&&profile.reduce_background_work!==false&&['worlds','directory'].includes(active.channel))active.interval*=Math.max(1,Number(profile.background_multiplier||2));
    const now=Date.now();
    const elapsed=now-Number(state.backgroundRefreshAt[active.channel]||0);
    if(elapsed<active.interval){scheduleBackgroundRefresh(Math.min(4000,Math.max(500,active.interval-elapsed)));return;}
    state.backgroundRefreshAt[active.channel]=now;
    state.backgroundRefreshBusy=true;
    try{
      if(active.channel==='worlds')await refreshWorldDiscoveryAndStatuses(true);
      else{
        const before=backgroundStateSignature(state.data,active.channel);
        const response=['directory','minimal'].includes(active.channel)?await api.invoke('state.get',{}):await api.invoke('server.runtime.status',{});
        const fresh=response?.state||response;
        if(fresh&&backgroundStateSignature(fresh,active.channel)!==before){
          state.data=fresh;
          window.__DWSYNC_STATE__=fresh;
          window.dispatchEvent(new CustomEvent('dragonwilds:state-updated',{detail:fresh}));
          render();
        }
      }
    }catch(_){/* The visible page keeps its last verified snapshot and retries later. */}
    finally{state.backgroundRefreshBusy=false;scheduleBackgroundRefresh(active.interval);}
  }

  function startBackgroundRefreshScheduler() {
    if(state.backgroundRefreshTimer)return;
    scheduleBackgroundRefresh(800);
    document.addEventListener('visibilitychange',()=>{if(!document.hidden)scheduleBackgroundRefresh(250);});
  }

  function operationMarkup() {
    if (!state.operation) return '';
    const operation=state.operation,percent=Math.max(0,Math.min(100,Number(operation.percent||0)));
    const phases=operation.phases||['connecting','comparing','downloading','unpacking','applying','verifying','profile','ready'];const active=Math.max(0,phases.indexOf(operation.phase||phases[0]));
    const counts=Number.isFinite(Number(operation.changed_files))?`<span>${Number(operation.changed_files||0)} changed</span><span>${Number(operation.unchanged_files||0)} unchanged</span>${operation.downloaded_bytes?`<span>${formatBytes(operation.downloaded_bytes)} transferred</span>`:''}`:'';
    const offset=operation.position||{x:0,y:0};
    return `<div class="operation-banner detailed" role="status" aria-live="polite" style="--operation-x:${Number(offset.x||0)}px;--operation-y:${Number(offset.y||0)}px"><span class="operation-spinner" aria-hidden="true"></span><div class="operation-progress-copy"><strong data-operation-drag-handle title="Drag this progress window">${escapeHtml(operation.title)}</strong><small data-operation-detail>${escapeHtml(operation.detail || 'This may take a moment. The application is still working.')}</small><div class="operation-progress-track"><i data-operation-progress style="width:${percent}%"></i></div><div class="operation-phases">${phases.map((phase,index)=>`<span data-operation-phase="${phase}" class="${index<active?'complete':index===active?'active':''}">${phase==='profile'?'Profile':phase[0].toUpperCase()+phase.slice(1)}</span>`).join('')}</div><div class="operation-counts" data-operation-counts>${counts}</div><small class="operation-diagnostic-state">Connection report: ${operation.diagnostics?'ON · saved to Downloads':'OFF · enable in Settings → Networking'}</small></div><b data-operation-percent>${Math.round(percent)}%</b></div>`;
  }

  document.addEventListener('pointerdown',(event)=>{
    const handle=event.target.closest?.('[data-operation-drag-handle]');if(!handle||!state.operation)return;
    event.preventDefault();const startX=event.clientX,startY=event.clientY,start={...(state.operation.position||{x:0,y:0})};
    const banner=handle.closest('.operation-banner');
    const move=(e)=>{const x=start.x+e.clientX-startX,y=start.y+e.clientY-startY;state.operation.position={x,y};banner?.style.setProperty('--operation-x',`${x}px`);banner?.style.setProperty('--operation-y',`${y}px`);};
    const up=()=>{window.removeEventListener('pointermove',move);};
    window.addEventListener('pointermove',move);window.addEventListener('pointerup',up,{once:true});
  });

  async function runOperation(title, detail, task) {
    if (state.operation) throw new Error(`${state.operation.title} is already in progress.`);
    state.operation = {title, detail}; render();
    try { return await task(); }
    finally { state.operation = null; render(); }
  }

  function setData(next) {
    state.data = next;
    seedPersistedInventories(next);
    window.__DWSYNC_STATE__ = next;
    window.dispatchEvent(new CustomEvent('dragonwilds:state-updated', { detail: next }));
    if (!state.selectedWorldId) state.selectedWorldId = next?.client?.active_world_id || null;
    if (!state.selectedServerWorldId) state.selectedServerWorldId = next?.server?.active_world_id || null;
    render();
  }

  function player() { return state.data?.player_profile || {}; }
  function worlds() { return state.data?.client?.worlds || []; }
  function curatedWorlds() { return state.data?.client?.curated_worlds || []; }
  function sharedWorldProfiles() { return state.data?.client?.shared_worlds?.profiles || []; } // legacy v2 compatibility only
  function browserWorlds() {
    const result = []; const seen = new Set();
    [...worlds(), ...(state.data?.client?.discovered_worlds || []), ...(state.data?.client?.directory_worlds || []), ...curatedWorlds()].forEach((world) => {
      const key = String(world?.id || ''); if (!key || seen.has(key)) return; seen.add(key); result.push(world);
    });
    return result;
  }
  // Connected LAN, Direct Connect, and manual Worlds live in client.worlds.
  // Route additions back to the view that actually renders that collection.
  function revealConnectedWorld(worldId) {
    if (worldId) state.selectedWorldId = worldId;
    state.data = state.data || {};
    state.data.client = state.data.client || {};
    const browser = state.data.client.world_browser = state.data.client.world_browser || {};
    browser.tab = 'direct'; browser.filter = 'all'; browser.search = ''; browser.page = 1;
    if (state.route === 'world-management') state.worldManagementTab = 'connected';
    else state.route = 'worlds';
  }
  function mergeConnectedWorld(world) {
    if (!world?.id || !state.data?.client) return null;
    const rows=state.data.client.worlds ||= [];
    const index=rows.findIndex((row)=>String(row?.id||'')===String(world.id));
    if(index<0)rows.push(world);else{
      const current=rows[index]||{};
      rows[index]={...current,...world,
        identity:{...(current.identity||{}),...(world.identity||{})},
        connection:{...(current.connection||{}),...(world.connection||{})},
        credentials:{...(current.credentials||{}),...(world.credentials||{})},
        presentation:{...(current.presentation||{}),...(world.presentation||{})},
        manifest_cache:{...(current.manifest_cache||{}),...(world.manifest_cache||{})},
        shared:{...(current.shared||{}),...(world.shared||{})},
        status:{...(current.status||{}),...(world.status||{})}};
    }
    state.data.client.active_world_id=world.id;
    return rows[index<0?rows.length-1:index];
  }
  function applyWorldBrowser(browser={}) {
    if(!state.data?.client)return;
    state.data.client.world_browser={...(state.data.client.world_browser||{}),...browser};
  }
  function privateWorlds() { return state.data?.client?.private_worlds || (state.data?.client?.singleplayer ? [state.data.client.singleplayer] : []); }
  function privateWorldById(id) { return privateWorlds().find((w)=>String(w.id)===String(id||'')) || null; }
  function singleplayerWorld() { const active=state.data?.client?.active_private_world_id; return privateWorldById(active) || privateWorldById('singleplayer') || state.data?.client?.singleplayer || null; }
  function anyClientWorld(id) { return browserWorlds().find((w)=>w.id===id) || sharedWorldProfiles().find((w)=>w.id===id) || privateWorldById(id); }
  function activeWorld() { return browserWorlds().find((w) => String(w.id) === String(state.selectedWorldId||'')) || privateWorldById(state.selectedWorldId) || null; }
  function serverWorlds() { return state.data?.server_profiles || []; }
  function activeServerWorld() { return serverWorlds().find((w) => w.id === state.selectedServerWorldId) || null; }

  function cachedProfileMods(profile) {
    const cache=profile?.metadata_cache;
    return Array.isArray(cache?.mods) ? cache.mods.map((unit)=>({...unit})) : null;
  }

  function seedPersistedInventories(data=state.data) {
    for (const world of data?.client?.private_worlds || []) {
      const cached=cachedProfileMods(world);
      if(cached) state.privateInventory[world.id]=cached;
    }
    for (const world of data?.server_profiles || []) {
      const cached=cachedProfileMods(world);
      if(cached) state.serverInventory[world.id]=cached;
    }
    const selected=String(state.selectedWorldId||data?.client?.active_private_world_id||'');
    if(selected && Array.isArray(state.privateInventory[selected])) state.singleplayerInventory=state.privateInventory[selected];
  }

  function selectedPrivateProfileId() {
    const selected=privateWorldById(state.selectedWorldId);
    return String(selected?.id || state.data?.client?.active_private_world_id || singleplayerWorld()?.id || 'singleplayer');
  }

  function privateProfileParams(extra={}) { return {profile_id:selectedPrivateProfileId(),id:selectedPrivateProfileId(),...extra}; }

  function currentLocationSnapshot() {
    return { route: state.route, selectedWorldId: state.selectedWorldId, selectedServerWorldId: state.selectedServerWorldId, serverTab: state.serverTab, serversTab: state.serversTab, privateTab: state.privateTab, profileTab: state.profileTab, settingsTab: state.settingsTab };
  }

  function pushNavigation() {
    const snap = currentLocationSnapshot();
    const last = state.navigationHistory[state.navigationHistory.length - 1];
    if (!last || JSON.stringify(last) !== JSON.stringify(snap)) state.navigationHistory.push(snap);
    if (state.navigationHistory.length > 40) state.navigationHistory.shift();
  }

  function navigateTo(route, patch = {}, remember = true) {
    if (remember) pushNavigation();
    stopPlayerPolling();
    Object.assign(state, patch || {});
    state.route = route;
    render();
  }

  function goBack() {
    const previous = state.navigationHistory.pop();
    if (!previous) return;
    stopPlayerPolling();
    Object.assign(state, previous);
    render();
    if (state.route === 'worlds') refreshAllWorldStatuses(true).catch(()=>{});
    // Live player telemetry belongs to hosted World management. Profile pages
    // show save-backed character history and never start a background poller.
  }

  async function handleRouteNavigation(route) {
    const next = String(route || '').trim();
    if (!next) return;
    if (next === 'trash') {
      window.__DWSYNC_OPEN_TRASH__?.();
      return;
    }
    const nextAppy=appyForRoute(next);
    rememberLastAppy(nextAppy);
    scheduleAppyWarm(nextAppy,{delay:180,timeout:1200});
    if(state.backgroundRefreshTimer)scheduleBackgroundRefresh(250);
    if (next === 'characters-app') { await enterRsdwToolkit(); return; }
    if (next === 'mods-app') {
      state.settingsTab='mods';
      if (state.route !== 'mods-app') navigateTo('mods-app');
      void loadModRepository({force:false,paint:true}).catch(()=>{});
      return;
    }
    if (next === 'rsdragonwilds-app') { state.worldManagementTab='server-setup';await handleRouteNavigation('world-management'); return; }
    if (next === 'servers' && next === state.route && state.serversTab !== 'worlds') { state.serversTab = 'worlds'; render(); return; }
    if (next === 'servers') state.serversTab = 'worlds';
    // Sync owns its complete four-tab workspace.  Remote Server remains a
    // separate focused route, but opening Sync must never replace its saved
    // configuration tab with the remote login surface.
    if (next === 'webhost' && state.route !== 'webhost') state.webhostTab = 'settings';
    if (next === 'rsdw-toolkit') { state.profileTab = 'characters'; await enterRsdwToolkit(); return; }
    if (next === state.route) {
      if (next === 'worlds') await refreshWorldDiscoveryAndStatuses(true);
      return;
    }
    navigateTo(next);
    if (next === 'profile') {
      state.profileTab = state.profileTab || 'user';
      try { const response = await api.invoke('characters.list', {}); state.characters = response.characters || []; state.rsdwWorlds = response.worlds || []; if (state.route === 'profile') render(); } catch (_) {}
    }
    if (next === 'worlds') await refreshWorldDiscoveryAndStatuses(true);
  }

  function installPersistentRouteDelegation() {
    if (root.dataset.routeDelegation === '1') return;
    root.dataset.routeDelegation = '1';
    root.addEventListener('click', (event) => {
      const el = event.target?.closest?.('[data-route]');
      if (!el || !root.contains(el)) return;
      event.preventDefault();
      event.stopPropagation();
      handleRouteNavigation(el.dataset.route).catch((error) => {
        toast('Navigation failed', error?.message || 'Could not open that area.', 'error');
        console.error('Dragonwilds Sync route navigation failed', el.dataset.route, error);
      });
    });
    root.addEventListener('pointerover',(event)=>{
      const button=event.target?.closest?.('.appy-nav[data-appy]');
      if(!button||!root.contains(button))return;
      scheduleAppyWarm(button.dataset.appy,{delay:140,timeout:1200});
    },{passive:true});
    root.addEventListener('pointerout',(event)=>{
      const button=event.target?.closest?.('.appy-nav[data-appy]');
      if(!button||button.contains(event.relatedTarget))return;
      cancelScheduledAppyWarm(button.dataset.appy);
    },{passive:true});
  }

  function hostingFocusMarkup() {
    if(!hostingFocusActive())return '';
    const profile=activeComputerProfile();
    const profileId=String(state.data?.server?.runtime?.active_profile_id||state.data?.server?.active_world_id||'');
    if(profileId&&state.hostingFocusDismissedProfileId===profileId)return '';
    const mode=String(profile.effective_mode||'balanced').replaceAll('_',' ');
    return `<div class="hosting-focus-banner" role="status"><span aria-hidden="true">◈</span><div><strong>Hosting Focus is active</strong><small>${escapeHtml(mode)} profile · launcher background work is reduced while the server runs</small></div><button type="button" id="dismiss-hosting-focus" aria-label="Dismiss Hosting Focus banner" title="Dismiss">×</button></div>`;
  }

  function scrollKey() {
    if (state.route === 'world-detail') return `world-detail:${state.selectedWorldId || ''}`;
    if (state.route === 'server-detail') return `server-detail:${state.selectedServerWorldId || ''}`;
    return state.route || 'worlds';
  }

  function discordSettings() { return state.data?.application?.integrations?.discord_rich_presence || {}; }

  function scheduleDiscordPresence(mode, world = null, extra = {}) {
    if (state.discordPresenceInputTimer) window.clearTimeout(state.discordPresenceInputTimer);
    state.discordPresenceInputTimer = window.setTimeout(() => {
      state.discordPresenceInputTimer = null;
      void setDiscordPresence(mode, world, extra);
    }, 300);
  }

  async function setDiscordPresence(mode, world = null, extra = {}) {
    const cfg = discordSettings();
    if (!window.dragonwilds?.discordActivity) return;
    if (cfg.enabled === false) {
      state.discordPresenceKey = '';
      try { await window.dragonwilds.discordClear(); } catch (_) {}
      return;
    }
    const name = String(world?.name || world?.nickname || world?.identity?.world_name || extra.worldName || '').trim();
    const showWorld = cfg.show_world !== false;
    const details = showWorld && name ? `${mode}: ${name}` : mode;
    const health = extra.health?.score != null && cfg.show_server_health ? `Health ${Math.round(Number(extra.health.score))}` : '';
    const players = extra.playerCount != null && cfg.show_player_count !== false ? `${extra.playerCount} player${Number(extra.playerCount) === 1 ? '' : 's'}` : '';
    const modeState = extra.state || (world?.kind === 'singleplayer' ? 'Local World' : world?.kind === 'linked' ? 'Connected World' : world ? 'DragonLink-Connect World' : 'Desktop launcher');
    const stateText = [players, health, modeState].filter(Boolean).join(' · ');
    const key = `${details}|${stateText}`;
    if (!extra.force && key === state.discordPresenceKey) return;
    if (!state.discordPresenceStartedAt || extra.resetTimer || state.discordPresenceKey.split('|')[0] !== details) state.discordPresenceStartedAt = Math.floor(Date.now() / 1000);
    state.discordPresenceKey = key;
    try {
      await window.dragonwilds.discordActivity({
        details,
        state: stateText,
        startTimestamp: state.discordPresenceStartedAt,
        largeImage: 'dragonwilds_sync',
        largeText: 'Dragonwilds Sync',
        smallImage: extra.smallImage || 'dragonwilds_sync',
        smallText: extra.smallText || mode,
        partySize: extra.playerCount,
        partyMax: extra.playerMax,
        buttons: [
          { label: 'Dragonwilds Sync', url: 'https://gh0sted5456-us.github.io/Dragonwilds-Sync-Web/' },
          { label: 'View on GitHub', url: 'https://github.com/gh0sted5456-us/Dragonwilds-Sync' },
        ],
      });
    } catch (_) { /* Discord is optional; launcher state must never depend on it. */ }
  }

  function updateDiscordPresenceForRoute() {
    if (!state.entered) return;
    if (state.route === 'world-detail' && activeWorld()) {
      const w = activeWorld();
      setDiscordPresence('Viewing World', w, { playerCount: w.status?.player_count, health: w.status?.server_health || w.manifest_cache?.server_health });
      return;
    }
    if (state.route === 'server-detail' && activeServerWorld()) {
      const w = activeServerWorld();
      const runtime = state.data?.server?.runtime || {};
      if (state.serverTab === 'maintenance') setDiscordPresence('Maintaining World', w, { playerCount: runtime.player_count, health: runtime.server_health });
      else if (runtime.running && runtime.active_profile_id === w.id) setDiscordPresence('Hosting World', w, { playerCount: runtime.player_count, health: runtime.server_health });
      else setDiscordPresence('Viewing World', w, { playerCount: runtime.player_count, health: runtime.server_health });
      return;
    }
    if (state.route === 'world-management') setDiscordPresence('Managing Worlds', null);
    else if (state.route === 'characters-app') setDiscordPresence('Editing Characters', null, { state: state.characterSelectedId ? 'Live 3D Character Studio' : 'Character Library' });
    else if (state.route === 'mods-app') setDiscordPresence('Managing Mods', null, { state: `${state.modExplorerScope === 'server' ? 'Server' : 'Player'} Mod Repository` });
    else if (state.route === 'rsdw-launcher') setDiscordPresence('Using RSDW-L', null, { state: 'Dragonwilds Toolkit' });
    else if (state.route === 'webhost') setDiscordPresence('Managing Sync', null, { state: 'Web Hosting' });
    else if (state.route === 'profile') setDiscordPresence('Viewing Profile', null, { state: 'Dragonwilds Sync' });
    else if (state.route === 'servers') setDiscordPresence('Managing Servers', null);
    else if (state.route === 'singleplayer') setDiscordPresence('Managing SinglePlayer', singleplayerWorld());
    else if (state.route === 'private-worlds' || state.route === 'singleplayer') setDiscordPresence('Managing Worlds', null);
    else if (state.route === 'worlds') setDiscordPresence('Browsing Worlds', null);
    else if (state.route === 'help') setDiscordPresence('Reading Help', null);
    else if (state.route === 'settings') setDiscordPresence('Configuring Dragonwilds Sync', null, { state: `${String(state.settingsTab||'application').replaceAll('-',' ')} settings` });
    else setDiscordPresence('Using Dragonwilds Sync', null);
  }

  async function openSteamCloudSettings() {
    try {
      const opened = await window.dragonwilds.openExternal('steam://nav/games/details/1374490');
      if (!opened) throw new Error('Steam did not accept the game settings link.');
      toast('Dragonwilds opened in Steam', 'Select the gear icon, then Properties > General, and disable Steam Cloud.', 'success');
    } catch (error) {
      toast('Could not open Steam', error?.message || 'Open Dragonwilds in your Steam Library, then use Properties > General.', 'error');
    }
  }

  function gpuListMarkup(hw = {}) {
    const gpus = Array.isArray(hw.gpus) ? hw.gpus : [];
    if (!gpus.length) return metric('GPU', hw.primary_gpu || hw.gpu || '—');
    return `<div class="metric gpu-metric"><span>GPUs</span><div class="gpu-list">${gpus.map((gpu, index) => {
      const name = typeof gpu === 'string' ? gpu : (gpu.name || gpu.model || 'GPU');
      const primary = name === hw.primary_gpu || gpu.primary || index === Number(hw.primary_gpu_index);
      return `<div title="${escapeHtml(name)}"><strong>${escapeHtml(name)}</strong>${primary ? '<em>HIGH PERFORMANCE</em>' : ''}</div>`;
    }).join('')}</div></div>`;
  }

  async function refreshSinglePlayerInventory(quiet = false, rescan = false) {
    try {
      const profileId=selectedPrivateProfileId();
      const response = await api.invoke('singleplayer.inventory', privateProfileParams({rescan}));
      state.singleplayerInventory = response.units || []; state.privateInventory[profileId]=state.singleplayerInventory; if (response.state) state.data = response.state;
      const warnings = response.warnings || [];
      if (!quiet) toast('SinglePlayer mods refreshed', `${state.singleplayerInventory.length} mod unit(s)${warnings.length ? ` · ${warnings.length} skipped` : ''}`, warnings.length ? 'warning' : 'success');
      if (warnings.length) toast('Some mods were skipped', warnings.slice(0, 3).join(' · '), 'warning');
      if (state.route === 'world-detail' && activeWorld()?.kind === 'singleplayer') render(); maybeScheduleNexusAutoCheck('singleplayer');
    }
    catch (error) { if (!quiet) toast('SinglePlayer mod scan failed', error.message, 'error'); }
  }

  async function refreshStarterCharacters(world = activeServerWorld(), quiet = true) {
    if (!world) return;
    try { const [response,submissions]=await Promise.all([api.invoke('server.world.starter_characters.list',{id:world.id}),api.invoke('server.world.character_submissions.list',{id:world.id})]); state.serverStarterCharacters[world.id]=response.characters||[];state.serverCharacterSubmissions[world.id]=submissions.submissions||[];if(!quiet)toast('Character sharing refreshed',`${state.serverStarterCharacters[world.id].length} approved · ${state.serverCharacterSubmissions[world.id].length} quarantined`,'success'); }
    catch(error){ if(!quiet)toast('Starter character list failed',error.message,'error'); }
  }

  async function refreshServerInventory(world = activeServerWorld(), quiet = false, rescan = false) {
    if (!world) return;
    try {
      const response = await api.invoke('server.world.inventory', { id: world.id, rescan });
      state.serverInventory[world.id] = response.units || [];
      const warnings = response.warnings || [];
      if (!quiet) toast('Mod inventory refreshed', `${state.serverInventory[world.id].length} unit(s) found${warnings.length ? ` · ${warnings.length} skipped` : ''}`, warnings.length ? 'warning' : 'success');
      if (warnings.length) toast('Some mods were skipped', warnings.slice(0, 3).join(' · '), 'warning');
      render();
      maybeScheduleNexusAutoCheck('server', world.id);
    } catch (error) { if (!quiet) toast('Mod scan failed', error.message, 'error'); }
  }

  async function refreshServerAccessConnections(quiet = true) {
    try {
      const response = await api.invoke('server.access.connections', {});
      state.serverAccessConnections = response.connections || [];
      state.serverAccessConnectionsLoadedAt = Date.now();
      render();
      if (!quiet) toast('Connections refreshed', `${state.serverAccessConnections.length} connected IP(s)`, 'success');
    } catch (error) { if (!quiet) toast('Could not load connections', error.message, 'error'); }
  }

  async function kickServerConnection(ip) {
    try {
      const response = await api.invoke('server.access.kick', { ip });
      toast(response.revoked ? 'Kicked' : 'Nothing to kick', response.revoked ? `${ip} must re-authenticate to sync again.` : `${ip} had no active session.`, response.revoked ? 'success' : 'warning');
      await refreshServerAccessConnections();
    } catch (error) { toast('Kick failed', error.message, 'error'); }
  }

  async function blockServerConnectionIp(ip) {
    if (!await managedConfirm(`Block ${ip} from this and every hosted World? This also kicks their current session.`, 'Block IP')) return;
    try {
      await api.invoke('server.access.block_ip', { ip });
      toast('IP blocked', `${ip} added to the global access policy and kicked.`, 'success');
      await refreshServerAccessConnections();
    } catch (error) { toast('Block failed', error.message, 'error'); }
  }

  async function blockServerConnectionProfile(profileId, ip) {
    if (!profileId) return toast('Profile ID unavailable', 'This client did not include a Profile ID in its Sync handshake. Block its IP instead.', 'warning');
    if (!await managedConfirm(`Block Sync Profile ${profileId} from every hosted World? Its current session will also be kicked.`, 'Block Profile')) return;
    try {
      const current=state.data?.application?.server_access_policy||{};
      const ids=[...new Set([...(current.blocked_profile_ids||[]),profileId])];
      await updateApplication({server_access_policy:{...current,blocked_profile_ids:ids}});
      if(ip)await api.invoke('server.access.kick',{ip});
      toast('Profile blocked', `${profileId} was added to the global Sync access policy.`, 'success');
      await refreshServerAccessConnections();
    } catch(error){toast('Profile block failed',error.message,'error');}
  }

  async function refreshServerBackups(world = activeServerWorld(), quiet = false) {
    if (!world) return;
    try {
      state.serverBackups[world.id] = await api.invoke('server.backups.list', { id: world.id }) || [];
      if (!quiet) toast('Backup list refreshed', `${state.serverBackups[world.id].length} backup(s)`, 'success');
      render();
    } catch (error) { if (!quiet) toast('Could not load backups', error.message, 'error'); }
  }

  async function refreshWorldMaintenance(world = activeServerWorld(), quiet = false) {
    if (!world) return;
    try {
      const [configsResult, saveResult, backupsResult] = await Promise.allSettled([
        api.invoke('server.world.config.list', { id: world.id }),
        api.invoke('server.world.save.status', { id: world.id }),
        api.invoke('server.backups.list', { id: world.id }),
      ]);
      if (configsResult.status !== 'fulfilled') throw configsResult.reason;
      const configs = configsResult.value || {};
      const save = saveResult.status === 'fulfilled' ? (saveResult.value || {}) : {};
      state.serverConfigs[world.id] = configs.configs || [];
      state.serverSaveStatus[world.id] = save || {};
      state.serverBackups[world.id] = backupsResult.status === 'fulfilled' ? (backupsResult.value || []) : [];
      if (!quiet) toast('World maintenance refreshed', `${state.serverConfigs[world.id].length} JSON config(s) found`, 'success');
      render();
    } catch (error) { if (!quiet) toast('Could not load World maintenance', error.message, 'error'); }
  }

  async function refreshWorldSaveEditor(world, kind, quiet = true) {
    if (!world) return;
    try {
      const response = await api.invoke('world.save.editor.read', { id: world.id, kind });
      state.worldSaveEditors[`${kind}:${world.id}`] = response.save || null;
      if (!quiet) toast('World save parsed', `${response.save?.editable_count || 0} editable settings`, 'success');
      render();
    } catch (error) {
      state.worldSaveEditors[`${kind}:${world.id}`] = { error: error.message };
      if (!quiet) toast('World save unavailable', error.message, 'error');
      render();
    }
  }

  async function refreshServerFeedback(world = activeServerWorld(), quiet = false) {
    if (!world) return;
    try {
      state.serverFeedback[world.id] = await api.invoke('server.feedback.list', { id: world.id }) || [];
      if (!quiet) toast('Feedback refreshed', `${state.serverFeedback[world.id].length} entr${state.serverFeedback[world.id].length === 1 ? 'y' : 'ies'}`, 'success');
      render();
    } catch (error) { if (!quiet) toast('Could not load feedback', error.message, 'error'); }
  }

  async function refreshServerRuntime(quiet = true) {
    try { const response = await api.invoke('server.runtime.status', {}); state.data = response.state; if (!quiet) toast('Server status refreshed'); render(); }
    catch (error) { if (!quiet) toast('Status refresh failed', error.message, 'error'); }
  }

  function stopPlayerPolling() {
    if (state.playerPollTimer) clearInterval(state.playerPollTimer);
    state.playerPollTimer = null;
  }

  async function refreshServerPlayers(world = activeServerWorld(), quiet = true, rerender = true) {
    if (!world) return;
    try {
      const previous = state.serverPlayers[world.id] || {};
      const isPrivate = world.kind === 'singleplayer' || !!privateWorldById(world.id);
      const response = await api.invoke(isPrivate ? 'singleplayer.players.get' : 'server.players.get', isPrivate ? { profile_id: world.id } : { id: world.id });
      state.serverPlayers[world.id] = response.players || { players: [], recent_players: [], tracker_connected: false };
      state.serverMapConfig[world.id] = response.player_map || {};
      if (response.state) state.data = response.state;
      if (!quiet) toast('RSDW tracking refreshed', `${state.serverPlayers[world.id].player_count || 0} connected player(s)`, 'success');
      const beforeSignature = JSON.stringify([previous.tracker_connected, previous.player_count, previous.players, previous.recent_players]);
      const next = state.serverPlayers[world.id];
      const nextSignature = JSON.stringify([next.tracker_connected, next.player_count, next.players, next.recent_players]);
      if (rerender && beforeSignature !== nextSignature && backgroundRefreshAllowed() && ((state.route === 'server-detail' && ['players','map'].includes(state.serverTab)) || (state.route === 'world-detail' && activeWorld()?.kind === 'singleplayer' && ['players','map'].includes(state.privateTab)) || (state.route === 'profile' && ['characters','live-map'].includes(state.profileTab)))) render();
    } catch (error) { if (!quiet) toast('RSDW tracking unavailable', error.message, 'error'); }
  }

  async function refreshServerSpawner(world = activeServerWorld(), options = {}) {
    if (!world) return;
    const existing = state.serverSpawner[world.id] || { kind:'enemy', query:'', category:'', selectedPath:'', selectedName:'', lastAck:'' };
    const kind = options.kind || existing.kind || 'enemy';
    const query = options.query != null ? options.query : existing.query || '';
    const category = options.category != null ? options.category : existing.category || '';
    const page = options.page != null ? Math.max(0,Number(options.page)||0) : Math.max(0,Number(existing.page)||0);
    try {
      const response = await api.invoke('server.spawner.catalog', { id:world.id, kind, query, category, limit:2000, refresh:!!options.refresh });
      state.serverSpawner[world.id] = { ...existing, ...response, kind, query, category, page,
        selectedPath: kind === existing.kind ? existing.selectedPath : '', selectedName: kind === existing.kind ? existing.selectedName : '' };
      render();
      if (options.refresh && !options.quiet) toast('RSDW Spawn Catalog updated', `${response.count || 0} matching entries loaded from the replaceable module catalog.`, 'success');
    } catch (error) {
      state.serverSpawner[world.id] = { ...existing, kind, query, category, page, error:error.message };
      render();
      if (!options.quiet) toast('Spawner catalog unavailable', error.message, 'error');
    }
  }

  async function refreshServerConsole(world = activeServerWorld(), quiet = true, {paint=true} = {}) {
    if (!world) return;
    try {
      const [catalog,unified]=await Promise.all([
        api.invoke('server.console.catalog',{id:world.id,limit:200}),
        api.invoke('server.console.unified',{id:world.id,limit:500}),
      ]);
      const commands=objectRows(catalog?.catalog?.commands);
      const history=objectRows(unified?.entries||catalog?.history);
      state.serverConsole[world.id]={...catalog,catalog:{...(catalog?.catalog||{}),commands},unified,history};
      if(paint)render();
    } catch (error) {
      state.serverConsole[world.id] = { error:error.message, catalog:{commands:[]}, history:[] };
      if(paint)render();
      if (!quiet) toast('RSDWToolkit console unavailable', error.message, 'error');
    }
  }

  let pendingRuntimeConsoleInlineHost=null;

  function openUnifiedLaunchConsole(world = activeServerWorld(), options={}) {
    if(!world?.id)return;
    const inlineHost=options.inlineHost||null;
    if(!inlineHost&&!detachedMode&&window.dragonwilds?.openDetachedWindow){
      return window.dragonwilds.openDetachedWindow({route:'server-console',title:`Dragonwilds Sync · ${world.name||'Runtime Console'}`,width:1240,height:800,context:{selectedServerWorldId:world.id}});
    }
    const existing=[...(inlineHost?[inlineHost]:modalRoot.querySelectorAll('.desktop-window'))].find((item)=>String(item.dataset.unifiedLaunchConsole||'')===String(world.id));
    if(existing){if(!inlineHost){existing.classList.remove('minimized');focusDesktopWindow(existing);syncInternalTaskbar();}return existing;}
    pendingRuntimeConsoleInlineHost=inlineHost;
    const win=showModal(`<div class="modal-header"><div><div class="eyebrow">Dedicated Runtime · Live</div><h2>${escapeHtml(world.name||'World')} Runtime Console</h2><p>One fast runtime app for game output, UE4SS, RuneSchema, diagnostics, and commands.</p></div><button class="btn ghost compact-btn" id="detach-runtime-console" ${detachedMode?'hidden':''}>↗ Open in Window</button><button class="modal-close" data-close-modal>×</button></div><div class="modal-body runtime-console-app"><nav class="runtime-console-tabs" aria-label="Runtime Console subapps">${[['console','Console'],['native','UE4SS Tools'],['dumpers','Dumpers'],['runeschema','RuneSchema'],['settings','Settings']].map(([key,label])=>`<button class="btn ${key==='console'?'primary':'ghost'} compact-btn" data-runtime-console-tab="${key}">${label}</button>`).join('')}</nav><section class="unified-launch-console" data-runtime-console-panel="console"><div class="unified-launch-console-toolbar"><div class="unified-launch-console-filters">${[['all','ALL'],['game','GAME CMD'],['ue4ss','UE4SS'],['runeschema','RUNESCHEMA'],['server','SERVER'],['sync','SYNC']].map(([key,label])=>`<button class="btn ${key==='all'?'primary':'ghost'} compact-btn" data-launch-console-filter="${key}">${label} <span data-launch-console-count="${key}">0</span></button>`).join('')}</div><button class="btn ghost compact-btn" data-launch-console-refresh>Refresh</button></div><div class="unified-launch-console-stream" role="log" aria-live="polite"><div class="empty-state compact">Waiting for dedicated runtime output…</div></div><form class="unified-launch-console-command"><label class="unified-launch-console-command-target"><span>Send to</span><select class="select" data-launch-console-target-select>${[['game','GAME CMD'],['ue4ss','UE4SS / Unreal'],['runeschema','RuneSchema']].map(([key,label])=>`<option value="${key}">${label}</option>`).join('')}</select></label><label class="unified-launch-console-command-input"><span data-launch-console-target>RSDWToolkit command</span><input class="field console-input" data-launch-console-input maxlength="1023" placeholder="RSDWToolkit command"/></label><button class="btn primary" data-launch-console-run type="submit">Run</button></form><div class="unified-launch-console-paths"><div class="unified-launch-console-path-row"><code data-launch-console-log>Unified session log will appear here.</code><button class="btn ghost compact-btn" data-launch-console-log-copy type="button" title="Copy the log file path">Copy Path</button><button class="btn ghost compact-btn" data-launch-console-log-reveal type="button" title="Show DragonwildsSync.log in its folder">Reveal</button><button class="btn ghost compact-btn" data-launch-console-log-export type="button" title="Save a shareable .txt copy of this session's log">Export .txt…</button></div><div class="unified-launch-console-path-row"><code data-launch-console-ue4ss>UE4SS log will appear when the loader starts.</code><button class="btn ghost compact-btn" data-launch-console-ue4ss-reveal type="button" title="Show UE4SS.log in its folder">Reveal</button></div></div></section><section class="runtime-console-panel" data-runtime-console-panel="native" hidden><div class="panel-header"><div><h3>UE4SS Debugging Tools</h3><span class="panel-subtitle">Live View, Watches, Dumpers, BP Mods, and Lua Debugger operate inside the game process.</span></div><span class="status-pill unknown" data-native-console-status>CHECKING</span></div><div class="identity-box"><strong>Native memory tools stay native</strong><p>Sync can own normal logs and commands, but UE4SS's Live View/property editor and debugger cannot be embedded as web controls without rebuilding UE4SS. Enable its original tabbed window only when you need those native memory tools.</p></div><div class="runtime-console-action-row"><button class="btn primary" data-native-console-toggle>Enable original UE4SS tools next launch</button><span data-native-console-note>Sync remains the sole console by default.</span></div></section><section class="runtime-console-panel" data-runtime-console-panel="dumpers" hidden><div class="panel-header"><div><h3>Runtime Dumpers</h3><span class="panel-subtitle">Run supported UE4SS/RSDW dump operations without opening another console.</span></div></div><div class="runtime-console-tool-grid"><button class="runtime-console-tool" data-runtime-tool-command="dump.types"><strong>Generate Lua Types</strong><span>Regenerate UE4SS Lua type stubs.</span></button><button class="runtime-console-tool" data-runtime-tool-command="cvars.dump"><strong>Dump Console Commands &amp; CVars</strong><span>Capture the engine command/variable catalog and help output.</span></button></div><div class="identity-box"><strong>High-risk native dumpers</strong><p>Object, actor, header, mapping, and binding dumpers remain available in the original UE4SS Tools window because several can load gigabytes of assets or destabilize a live world.</p></div></section><section class="runtime-console-panel runeschema-panel" data-runtime-console-panel="runeschema" hidden data-runeschema-variant="unknown"><div class="panel-header"><div><h3>RuneSchema</h3><span class="panel-subtitle" data-runeschema-subtitle>Detecting installed build…</span></div><span class="status-pill unknown" data-runeschema-variant-pill>DETECTING</span></div><nav class="runtime-console-tabs runeschema-subtabs" aria-label="RuneSchema subapps">${[['overview','Overview'],['settings','Settings'],['generators','Generators'],['loadorder','Load Order'],['compatibility','Compatibility']].map(([key,label])=>`<button class="btn ${key==='overview'?'primary':'ghost'} compact-btn" data-runeschema-subtab="${key}">${label}</button>`).join('')}</nav><section class="runeschema-subpanel" data-runeschema-subpanel="overview"><div class="runtime-console-action-row"><button class="btn ghost compact-btn" data-runeschema-overview-refresh>Refresh Status</button><span data-runeschema-overview-note>Loading…</span></div><dl class="runeschema-overview-grid"><div><dt>Build</dt><dd data-runeschema-overview-version>—</dd></div><div><dt>Content mods</dt><dd data-runeschema-overview-mods>—</dd></div><div><dt>Tooling</dt><dd data-runeschema-overview-tooling>—</dd></div></dl><code data-runeschema-overview-config-path>Locating RuneSchema/config/config.json…</code><code data-runeschema-overview-mods-path>Locating RuneSchema/mods…</code><div class="identity-box" data-runeschema-experimental-only><strong>Overview, Settings, Load Order, and Compatibility</strong><p>These pages read and write the exact same files as RuneSchema's own in-game tab (config.json, mods.txt, compatibility_report.txt) -- either can edit what the other wrote.</p></div><div class="identity-box" data-runeschema-github-only hidden><strong>Official 0.6.0 build detected</strong><p>Load Order, Compatibility, and the tooling settings below are a 0.6.1 Experimental feature and are not available on this install. Only Overview, basic Settings, and JSON schema generation apply.</p></div></section><section class="runeschema-subpanel" data-runeschema-subpanel="settings" hidden><div class="runtime-console-action-row"><span data-runeschema-settings-note>Loading…</span><button class="btn primary" data-runeschema-settings-save disabled>Save Settings</button></div><div class="settings-row"><div class="settings-copy"><strong>Automatic reload</strong><span>Reload content mods automatically when their files change.</span></div><label class="switch"><input type="checkbox" data-runeschema-setting="enableAutoReload"/><span></span></label></div><div class="settings-row"><div class="settings-copy"><strong>Debug logging</strong><span>Verbose RuneSchema logging in UE4SS.log.</span></div><label class="switch"><input type="checkbox" data-runeschema-setting="enableDebugLogging"/><span></span></label></div><div class="settings-row" data-runeschema-experimental-only><div class="settings-copy"><strong>Experimental spawn drop scaling</strong><span>An explicit DropIncreasePercent multiplies supported drop rows. Scale alone never changes drops. Restart after changing.</span></div><label class="switch"><input type="checkbox" data-runeschema-setting="enableExperimentalDropScaling"/><span></span></label></div><div data-runeschema-experimental-only><h4 class="runeschema-settings-heading">Tooling</h4><div class="settings-row"><div class="settings-copy"><strong>Enable tooling</strong><span>Master switch for everything below.</span></div><label class="switch"><input type="checkbox" data-runeschema-setting="tooling.enabled"/><span></span></label></div><div class="settings-row"><div class="settings-copy"><strong>JSON schema generation</strong></div><label class="switch"><input type="checkbox" data-runeschema-setting="tooling.enableSchemaGeneration"/><span></span></label></div><div class="settings-row"><div class="settings-copy"><strong>FModel snippet generator</strong></div><label class="switch"><input type="checkbox" data-runeschema-setting="tooling.enableFModelSnippetGenerator"/><span></span></label></div><h4 class="runeschema-settings-heading">mods.txt</h4><div class="settings-row"><div class="settings-copy"><strong>Enable load-order file</strong></div><label class="switch"><input type="checkbox" data-runeschema-setting="tooling.modsTxt.enabled"/><span></span></label></div><div class="settings-row"><div class="settings-copy"><strong>Create automatically</strong></div><label class="switch"><input type="checkbox" data-runeschema-setting="tooling.modsTxt.autoCreate"/><span></span></label></div><div class="settings-row"><div class="settings-copy"><strong>Reconcile folders</strong></div><label class="switch"><input type="checkbox" data-runeschema-setting="tooling.modsTxt.reconcileFolders"/><span></span></label></div><div class="settings-row"><div class="settings-copy"><strong>Preserve comments</strong></div><label class="switch"><input type="checkbox" data-runeschema-setting="tooling.modsTxt.preserveComments"/><span></span></label></div><div class="settings-row"><div class="settings-copy"><strong>Require 0 or 1 values</strong></div><label class="switch"><input type="checkbox" data-runeschema-setting="tooling.modsTxt.strictValues"/><span></span></label></div><h4 class="runeschema-settings-heading">Compatibility reports</h4><div class="settings-row"><div class="settings-copy"><strong>Enable compatibility reports</strong></div><label class="switch"><input type="checkbox" data-runeschema-setting="tooling.compatibilityReports.enabled"/><span></span></label></div><div class="settings-row"><div class="settings-copy"><strong>Write compatibility_report.txt</strong></div><label class="switch"><input type="checkbox" data-runeschema-setting="tooling.compatibilityReports.writeFile"/><span></span></label></div><div class="settings-row"><div class="settings-copy"><strong>Warn on shared target</strong></div><label class="switch"><input type="checkbox" data-runeschema-setting="tooling.compatibilityReports.warnSameTarget"/><span></span></label></div><div class="settings-row"><div class="settings-copy"><strong>Warn on shared property</strong></div><label class="switch"><input type="checkbox" data-runeschema-setting="tooling.compatibilityReports.warnSameProperty"/><span></span></label></div><div class="settings-row"><div class="settings-copy"><strong>Warn on array replacement</strong></div><label class="switch"><input type="checkbox" data-runeschema-setting="tooling.compatibilityReports.warnArrayReplacement"/><span></span></label></div></div></section><section class="runeschema-subpanel" data-runeschema-subpanel="generators" hidden><div class="identity-box"><strong>JSON Schema Files</strong><p>Writes editor autocomplete schemas to Mods/RuneSchema/schemas. This reads live game reflection data, so it can only run from the World's own ImGui RuneSchema tab (UE4SS debug console enabled) -- not remotely from here. Run it after entering a world for full data-table coverage.</p></div><div class="runtime-console-action-row" data-runeschema-experimental-only><button class="btn primary" data-runeschema-fmodel-generate>Generate FModel Snippets</button><span data-runeschema-fmodel-note>Reads RuneSchema/config/fmodel-input, writes sanitized drafts to fmodel-snippets.</span></div><pre class="runeschema-report-output" data-runeschema-fmodel-output hidden></pre></section><section class="runeschema-subpanel" data-runeschema-subpanel="loadorder" hidden data-runeschema-experimental-only><div class="runtime-console-action-row"><button class="btn ghost compact-btn" data-runeschema-load-order-reconcile>Reconcile Now</button><button class="btn ghost compact-btn" data-runeschema-load-order-refresh>Refresh</button><button class="btn primary" data-runeschema-load-order-save disabled>Save Load Order</button></div><code data-runeschema-load-order-path>Locating RuneSchema/mods/mods.txt…</code><div class="runeschema-load-order-list" data-runeschema-load-order-list><div class="empty-state compact">Loading…</div></div><span data-runeschema-load-order-note></span></section><section class="runeschema-subpanel" data-runeschema-subpanel="compatibility" hidden data-runeschema-experimental-only><div class="runtime-console-action-row"><button class="btn primary" data-runeschema-compatibility-generate>Generate Compatibility Report</button><span data-runeschema-compatibility-note>Scans enabled content mods' JSON for likely load-order conflicts.</span></div><pre class="runeschema-report-output" data-runeschema-compatibility-output hidden></pre></section><button class="btn ghost" data-open-runeschema-configuration>Open this World's Configuration</button></section><section class="runtime-console-panel" data-runtime-console-panel="settings" hidden><div class="panel-header"><div><h3>Console Window Policy</h3><span class="panel-subtitle">Changes apply to the installed UE4SS runtime without rewriting unrelated settings.</span></div></div><div class="settings-row"><div class="settings-copy"><strong>Original game and UE4SS windows</strong><span>Off keeps Runtime Console as the sole console. On restores UE4SS's separate Debugging Tools and external console at the next server launch.</span></div><button class="btn ghost" data-native-console-toggle>Loading…</button></div><code data-native-console-path>Locating UE4SS-settings.ini…</code></section></div><div class="modal-footer"><span>Closing this window never stops the server or logging.</span><button class="btn ghost" data-close-modal>Close Runtime Console</button></div>`,{native:false,title:`${world.name||'World'} Runtime Console`,width:1240,height:800});
    win.dataset.unifiedLaunchConsole=String(world.id);
    let filter='all',busy=false,disposed=false,lastDrawKey='',hasDrawnConsole=false,followTail=true;
    const consoleToolbar=win.querySelector('.unified-launch-console-toolbar');
    if(consoleToolbar){const controls=document.createElement('div');controls.className='unified-launch-console-scroll';controls.innerHTML='<button class="btn ghost compact-btn" data-launch-console-top title="Scroll to oldest entry">↑ Top</button><button class="btn primary compact-btn" data-launch-console-follow aria-pressed="true" title="Keep following live output">● Live</button><button class="btn ghost compact-btn" data-launch-console-bottom title="Scroll to newest entry">↓ Bottom</button>';consoleToolbar.appendChild(controls);}
    const latestPaths={current:'',ue4ss:''};
    const draw=(payload)=>{
      if(disposed||!win.isConnected)return;
      const rows=(payload?.entries||[]).filter((row)=>filter==='all'||String(row.source||'server')===filter);
      const tail=rows[rows.length-1]||{};
      const drawKey=JSON.stringify([filter,rows.length,tail.ts||0,tail.source||'',tail.level||'',tail.message||'',payload?.counts||{},payload?.current_log||'',payload?.ue4ss_log||'']);
      if(drawKey===lastDrawKey)return;
      lastDrawKey=drawKey;
      const host=win.querySelector('.unified-launch-console-stream');if(!host)return;
      const stick=followTail||!hasDrawnConsole;
      host.innerHTML=rows.length?rows.map((row)=>{const source=String(row.source||'server').toLowerCase(),level=String(row.level||'info').toLowerCase(),when=new Date(Number(row.ts||0)*1000);return `<div class="unified-launch-console-row ${escapeHtml(source)} ${escapeHtml(level)}"><time>${escapeHtml(Number.isFinite(when.getTime())?when.toLocaleTimeString():'--')}</time><b>${escapeHtml(source.toUpperCase())}</b><span>${escapeHtml(row.message||'')}</span></div>`;}).join(''):'<div class="empty-state compact">No matching activity in this server session.</div>';
      const counts=payload?.counts||{},total=Object.values(counts).reduce((sum,value)=>sum+Number(value||0),0);win.querySelectorAll('[data-launch-console-count]').forEach((node)=>{node.textContent=String(node.dataset.launchConsoleCount==='all'?total:Number(counts[node.dataset.launchConsoleCount]||0));});
      latestPaths.current=payload?.current_log||'';latestPaths.ue4ss=payload?.ue4ss_log||'';
      const log=win.querySelector('[data-launch-console-log]');if(log){log.textContent=payload?.current_log||'Unified session log unavailable';log.title=payload?.current_log||'';}
      const ue4ss=win.querySelector('[data-launch-console-ue4ss]');if(ue4ss){ue4ss.textContent=payload?.ue4ss_log||'UE4SS log waiting for loader output';ue4ss.title=payload?.ue4ss_log||'';}
      if(stick){host.scrollTop=host.scrollHeight;requestAnimationFrame(()=>{if(host.isConnected)host.scrollTop=host.scrollHeight;});}
      hasDrawnConsole=true;
    };
    const refresh=async()=>{if(busy||disposed)return;busy=true;try{draw(await api.invoke('server.console.unified',{id:world.id,limit:800}));}catch(error){const host=win.querySelector('.unified-launch-console-stream');if(host)host.innerHTML=`<div class="warning-box"><strong>Console stream unavailable</strong><br/>${escapeHtml(error.message)}</div>`;}finally{busy=false;}};
    // Where a typed command goes is a standing choice about the operator's
    // intent, not something that should flip every time they click a log
    // filter chip -- the two used to be the same variable, which meant
    // clicking SERVER or SYNC (to just look at those logs) silently disabled
    // the command box entirely. commandTarget is now independent state, set
    // only by the "Send to" selector.
    let commandTarget=win.querySelector('[data-launch-console-target-select]')?.value||'game';
    const syncCommandTarget=()=>{const input=win.querySelector('[data-launch-console-input]'),label=win.querySelector('[data-launch-console-target]');const copy=commandTarget==='runeschema'?'RuneSchema console command':commandTarget==='ue4ss'?'UE4SS / Unreal console command':'RSDWToolkit game command';if(input)input.placeholder=copy;if(label)label.textContent=copy;};
    win.querySelector('[data-launch-console-target-select]')?.addEventListener('change',(event)=>{commandTarget=['game','ue4ss','runeschema'].includes(event.target.value)?event.target.value:'game';syncCommandTarget();win.querySelector('[data-launch-console-input]')?.focus();});
    syncCommandTarget();
    const consoleStream=win.querySelector('.unified-launch-console-stream'),followButton=win.querySelector('[data-launch-console-follow]');
    const paintFollow=()=>{if(!followButton)return;followButton.classList.toggle('primary',followTail);followButton.classList.toggle('ghost',!followTail);followButton.setAttribute('aria-pressed',String(followTail));followButton.textContent=followTail?'● Live':'○ Paused';};
    const scrollBottom=()=>{followTail=true;paintFollow();if(consoleStream)consoleStream.scrollTop=consoleStream.scrollHeight;};
    win.querySelector('[data-launch-console-top]')?.addEventListener('click',()=>{followTail=false;paintFollow();if(consoleStream)consoleStream.scrollTop=0;});
    win.querySelector('[data-launch-console-bottom]')?.addEventListener('click',scrollBottom);
    followButton?.addEventListener('click',()=>{followTail=!followTail;paintFollow();if(followTail)scrollBottom();});
    consoleStream?.addEventListener('scroll',()=>{if(!consoleStream||!followTail)return;if(consoleStream.scrollHeight-consoleStream.scrollTop-consoleStream.clientHeight>90){followTail=false;paintFollow();}});
    paintFollow();
    win.querySelectorAll('[data-launch-console-filter]').forEach((button,index)=>{button.setAttribute('aria-pressed',String(index===0));button.addEventListener('click',()=>{filter=button.dataset.launchConsoleFilter||'all';win.querySelectorAll('[data-launch-console-filter]').forEach((item)=>{const active=item===button;item.classList.toggle('primary',active);item.classList.toggle('ghost',!active);item.setAttribute('aria-pressed',String(active));});refresh();});});
    win.querySelector('.unified-launch-console-command')?.addEventListener('submit',async(event)=>{event.preventDefault();const input=win.querySelector('[data-launch-console-input]'),command=String(input?.value||'').trim();if(!command)return;const target=commandTarget==='runeschema'?'RuneSchema':commandTarget==='ue4ss'?'UE4SS / Unreal':'RSDWToolkit';if(!await managedConfirm(`Run this ${target} command?\n\n${command}`,'Confirm Console Command'))return;const run=win.querySelector('[data-launch-console-run]');if(run)run.disabled=true;try{const result=await api.invoke('server.console.execute',{id:world.id,command,target:commandTarget,confirmed:true,source:`desktop-${commandTarget}`,actor:'owner'});if(input)input.value='';toast(`${target} command acknowledged`,result?.ack||command,'success');await refresh();}catch(error){toast(`${target} command failed`,error.message,'error');await refresh();}finally{if(run)run.disabled=false;}});
    win.querySelector('[data-launch-console-refresh]')?.addEventListener('click',refresh);
    win.querySelector('[data-launch-console-log-copy]')?.addEventListener('click',async()=>{if(!latestPaths.current)return toast('Nothing to copy','The unified session log has not been created yet.','');await window.dragonwilds.copyText(latestPaths.current);toast('Log path copied',latestPaths.current,'success');});
    win.querySelector('[data-launch-console-log-reveal]')?.addEventListener('click',async()=>{if(!latestPaths.current)return toast('Nothing to reveal','The unified session log has not been created yet.','');const ok=await window.dragonwilds.revealPath?.(latestPaths.current);if(!ok)toast('Could not open folder',latestPaths.current,'error');});
    win.querySelector('[data-launch-console-ue4ss-reveal]')?.addEventListener('click',async()=>{if(!latestPaths.ue4ss)return toast('Nothing to reveal','UE4SS.log has not been written yet by the loader.','');const ok=await window.dragonwilds.revealPath?.(latestPaths.ue4ss);if(!ok)toast('Could not open folder',latestPaths.ue4ss,'error');});
    win.querySelector('[data-launch-console-log-export]')?.addEventListener('click',async()=>{
      if(!latestPaths.current)return toast('Nothing to export','The unified session log has not been created yet.','');
      const safeName=String(world.name||'World').replace(/[<>:"/\\|?*]/g,'_');
      const destination=await window.dragonwilds.saveFile({title:'Export Runtime Console Log',defaultPath:`${safeName}-console-log.txt`,filters:[{name:'Text log',extensions:['txt']}]});
      if(!destination)return;
      try{const result=await api.invoke('server.console.export_log',{id:world.id,destination});toast('Log exported',result?.destination||destination,'success');}
      catch(error){toast('Log export failed',error.message,'error');}
    });
    win.querySelectorAll('[data-runtime-console-tab]').forEach((button,index)=>{
      button.setAttribute('role','tab');button.setAttribute('aria-selected',String(index===0));
      button.addEventListener('click',()=>{
        const selected=button.dataset.runtimeConsoleTab||'console';
        win.querySelectorAll('[data-runtime-console-tab]').forEach((item)=>{const active=item===button;item.classList.toggle('primary',active);item.classList.toggle('ghost',!active);item.setAttribute('aria-selected',String(active));});
        win.querySelectorAll('[data-runtime-console-panel]').forEach((panel)=>{panel.hidden=panel.dataset.runtimeConsolePanel!==selected;});
        if(selected==='runeschema'&&!runeschemaOverviewLoaded)loadRuneschemaOverview();
      });
    });
    win.querySelector('#detach-runtime-console')?.addEventListener('click',async()=>{
      try{
        const opened=await popOutDesktopWindow(win,{title:`${world.name||'World'} Runtime Console`,width:1240,height:800});
        if(!opened)throw new Error('The lightweight native console host is unavailable.');
      }catch(error){toast('Runtime Console could not detach',error.message,'error');}
    });
    let runeschemaOverviewLoaded=false,runeschemaSettingsDraft=null,runeschemaLoadOrderEntries=null;
    const rsGet=(obj,path)=>path.split('.').reduce((node,key)=>(node&&typeof node==='object')?node[key]:undefined,obj);
    const rsSet=(obj,path,value)=>{const keys=path.split('.');let node=obj;for(let i=0;i<keys.length-1;i++){if(typeof node[keys[i]]!=='object'||node[keys[i]]===null)node[keys[i]]={};node=node[keys[i]];}node[keys[keys.length-1]]=value;};
    const runeschemaSettingsPanel=win.querySelector('[data-runeschema-subpanel="settings"]');
    if(runeschemaSettingsPanel){
      const advanced=document.createElement('div');advanced.dataset.runeschemaExperimentalOnly='';
      const toggles=(group,rows)=>`<h4 class="runeschema-settings-heading">${group}</h4>${rows.map(([path,label,note])=>`<div class="settings-row"><div class="settings-copy"><strong>${label}</strong>${note?`<span>${note}</span>`:''}</div><label class="switch"><input type="checkbox" data-runeschema-setting="${path}"/><span></span></label></div>`).join('')}`;
      advanced.innerHTML=
        toggles('Identity overrides',[
          ['identityOverrides.enabled','Enable identity overrides','Master switch for stable asset, recipe, and journal identity normalization.'],
          ['identityOverrides.assets','Assets','Normalize asset identities.'],['identityOverrides.recipes','Recipes','Normalize recipe identities.'],
          ['identityOverrides.journals','Journals','Normalize journal identities.'],['identityOverrides.dryRun','Dry run','Report changes without applying them.'],
          ['identityOverrides.logChanges','Log changes','Write applied identity changes to the RuneSchema log.']])+
        `<h4 class="runeschema-settings-heading">Spawn safety</h4><div class="settings-row"><div class="settings-copy"><strong>Maximum scale</strong><span>Hard cap applied by the experimental spawning controls.</span></div><input class="field compact-field" type="number" min="0" step="0.1" data-runeschema-setting="spawnSafety.maxScale"/></div><div class="settings-row"><div class="settings-copy"><strong>Maximum drop increase</strong><span>Upper percentage accepted by drop-scaling tools.</span></div><input class="field compact-field" type="number" min="0" step="1" data-runeschema-setting="spawnSafety.maxDropIncreasePercent"/></div>`+
        toggles('Generated schema types',[
          ['tooling.schemaTypes.utility','Utility'],['tooling.schemaTypes.assets','Assets'],['tooling.schemaTypes.blueprints','Blueprints'],
          ['tooling.schemaTypes.buildings','Buildings'],['tooling.schemaTypes.courses','Courses'],['tooling.schemaTypes.enums','Enums'],
          ['tooling.schemaTypes.journal','Journal'],['tooling.schemaTypes.raw','Raw'],['tooling.schemaTypes.recipes','Recipes'],
          ['tooling.schemaTypes.spawns','Spawns'],['tooling.schemaTypes.strings','Strings']]);
      runeschemaSettingsPanel.appendChild(advanced);
    }
    const runeschemaGeneratorsPanel=win.querySelector('[data-runeschema-subpanel="generators"]');
    if(runeschemaGeneratorsPanel){
      const capabilities=document.createElement('div');
      capabilities.className='identity-box runeschema-generator-capabilities';
      capabilities.dataset.runeschemaExperimentalOnly='';
      capabilities.innerHTML='<strong>0.6.3 Experimental generator functions</strong><p>Console Settings controls Utility, Assets, Blueprints, Buildings, Courses, Enums, Journal, Raw, Recipes, Spawns, and Strings. The selected functions are saved to this World\'s live RuneSchema config and are used by RuneSchema when generation runs in-game.</p>';
      runeschemaGeneratorsPanel.prepend(capabilities);
    }
    const applyRuneschemaVariant=(variant)=>{
      const panel=win.querySelector('[data-runtime-console-panel="runeschema"]');
      if(panel)panel.dataset.runeschemaVariant=variant||'unknown';
      const hideExperimental=variant==='github',hideGithub=variant!=='github';
      win.querySelectorAll('[data-runeschema-experimental-only]').forEach((el)=>{el.hidden=hideExperimental;});
      win.querySelectorAll('[data-runeschema-github-only]').forEach((el)=>{el.hidden=hideGithub;});
    };
    const paintRuneschemaOverview=(payload)=>{
      const variant=payload?.variant||'unknown';
      applyRuneschemaVariant(variant);
      const pill=win.querySelector('[data-runeschema-variant-pill]');
      if(pill){pill.textContent=variant==='experimental'?'0.6.3 EXPERIMENTAL':variant==='github'?'OFFICIAL':'UNKNOWN BUILD';pill.className=`status-pill ${variant==='experimental'?'online':variant==='github'?'unknown':'offline'}`;}
      const subtitle=win.querySelector('[data-runeschema-subtitle]');
      if(subtitle)subtitle.textContent=payload?.config_exists?`Detected via ${payload.variant_source==='ue4ss_log'?'UE4SS.log':'config.json shape'}.`:'RuneSchema config.json not found for this World yet.';
      const note=win.querySelector('[data-runeschema-overview-note]');
      if(note)note.textContent=payload?.config_exists?'Loaded.':'This World has not launched with RuneSchema installed yet.';
      const versionEl=win.querySelector('[data-runeschema-overview-version]');
      if(versionEl)versionEl.textContent=payload?.version?`${payload.version} (${payload.variant_source==='ue4ss_log'?'log-verified':'inferred from config'})`:'Not detected';
      const modsEl=win.querySelector('[data-runeschema-overview-mods]');
      if(modsEl)modsEl.textContent=payload?.mod_count!=null?`${payload.mod_count} folder${payload.mod_count===1?'':'s'} in Mods/RuneSchema/mods`:'—';
      const toolingEl=win.querySelector('[data-runeschema-overview-tooling]');
      if(toolingEl)toolingEl.textContent=variant==='experimental'?(payload?.tooling_enabled?'Enabled':'Disabled'):'Not available on this build';
      const configPath=win.querySelector('[data-runeschema-overview-config-path]');
      if(configPath){configPath.textContent=payload?.config_path||'RuneSchema config.json unavailable';configPath.title=payload?.config_path||'';}
      const modsPath=win.querySelector('[data-runeschema-overview-mods-path]');
      if(modsPath){modsPath.textContent=payload?.mods_path||'RuneSchema mods folder unavailable';modsPath.title=payload?.mods_path||'';}
    };
    const paintRuneschemaSettings=(settings)=>{
      runeschemaSettingsDraft=JSON.parse(JSON.stringify(settings||{}));
      win.querySelectorAll('[data-runeschema-setting]').forEach((input)=>{const value=rsGet(runeschemaSettingsDraft,input.dataset.runeschemaSetting);if(input.type==='checkbox')input.checked=!!value;else input.value=value??'';});
      const note=win.querySelector('[data-runeschema-settings-note]');
      if(note)note.textContent='Loaded from config.json.';
      const save=win.querySelector('[data-runeschema-settings-save]');
      if(save)save.disabled=true;
    };
    const loadRuneschemaOverview=async()=>{
      const note=win.querySelector('[data-runeschema-overview-note]');
      try{
        const payload=await api.invoke('server.console.runeschema.overview',{id:world.id});
        runeschemaOverviewLoaded=true;
        paintRuneschemaOverview(payload);
        paintRuneschemaSettings(payload?.settings);
      }catch(error){
        runeschemaOverviewLoaded=false;
        if(note)note.textContent=error.message;
        const pill=win.querySelector('[data-runeschema-variant-pill]');
        if(pill){pill.textContent='UNAVAILABLE';pill.className='status-pill offline';}
      }
    };
    win.querySelector('[data-runeschema-overview-refresh]')?.addEventListener('click',()=>loadRuneschemaOverview());
    win.querySelectorAll('[data-runeschema-setting]').forEach((input)=>input.addEventListener('change',()=>{
      if(!runeschemaSettingsDraft)return;
      rsSet(runeschemaSettingsDraft,input.dataset.runeschemaSetting,input.type==='checkbox'?input.checked:(input.type==='number'?Number(input.value):input.value));
      const save=win.querySelector('[data-runeschema-settings-save]');
      if(save)save.disabled=false;
      const note=win.querySelector('[data-runeschema-settings-note]');
      if(note)note.textContent='Unsaved changes.';
    }));
    win.querySelector('[data-runeschema-settings-save]')?.addEventListener('click',async()=>{
      const save=win.querySelector('[data-runeschema-settings-save]');
      if(!runeschemaSettingsDraft||!save)return;
      save.disabled=true;
      try{const payload=await api.invoke('server.console.runeschema.settings.write',{id:world.id,settings:runeschemaSettingsDraft});paintRuneschemaSettings(payload?.settings||runeschemaSettingsDraft);toast('RuneSchema settings saved',payload?.path||'config.json','success');}
      catch(error){toast('RuneSchema settings not saved',error.message,'error');save.disabled=false;}
    });
    const paintRuneschemaLoadOrder=(payload)=>{
      runeschemaLoadOrderEntries=Array.isArray(payload?.entries)?payload.entries.map((entry)=>({name:entry.name,enabled:!!entry.enabled})):[];
      const path=win.querySelector('[data-runeschema-load-order-path]');
      if(path){path.textContent=payload?.mods_path||'RuneSchema mods/mods.txt unavailable';path.title=payload?.mods_path||'';}
      const list=win.querySelector('[data-runeschema-load-order-list]');
      if(list){
        list.innerHTML=runeschemaLoadOrderEntries.length?runeschemaLoadOrderEntries.map((entry,index)=>`<div class="runeschema-load-order-row"><label class="switch"><input type="checkbox" data-runeschema-load-order-enabled data-index="${index}" ${entry.enabled?'checked':''}/><span></span></label><span class="runeschema-load-order-name">${escapeHtml(entry.name)}</span><div class="runeschema-load-order-move"><button type="button" class="btn ghost compact-btn" data-runeschema-load-order-up data-index="${index}" ${index===0?'disabled':''}>&uarr;</button><button type="button" class="btn ghost compact-btn" data-runeschema-load-order-down data-index="${index}" ${index===runeschemaLoadOrderEntries.length-1?'disabled':''}>&darr;</button></div></div>`).join(''):'<div class="empty-state compact">No content mods discovered under Mods/RuneSchema/mods.</div>';
      }
      const note=win.querySelector('[data-runeschema-load-order-note]');
      if(note)note.textContent=payload?.note||(payload?.changed?'Reconciled against folders on disk and saved.':'Matches folders on disk.');
      const save=win.querySelector('[data-runeschema-load-order-save]');
      if(save)save.disabled=true;
    };
    const loadRuneschemaLoadOrder=async()=>{
      const note=win.querySelector('[data-runeschema-load-order-note]');
      if(note)note.textContent='Loading…';
      try{const payload=await api.invoke('server.console.runeschema.load_order.read',{id:world.id});paintRuneschemaLoadOrder(payload);}
      catch(error){if(note)note.textContent=error.message;}
    };
    win.querySelector('[data-runeschema-load-order-refresh]')?.addEventListener('click',()=>loadRuneschemaLoadOrder());
    win.querySelector('[data-runeschema-load-order-reconcile]')?.addEventListener('click',async()=>{
      const button=win.querySelector('[data-runeschema-load-order-reconcile]');
      if(button)button.disabled=true;
      try{const payload=await api.invoke('server.console.runeschema.load_order.reconcile',{id:world.id});paintRuneschemaLoadOrder(payload);toast('Load order reconciled',payload?.changed?'mods.txt was updated to match folders on disk.':'Already matched folders on disk.','success');}
      catch(error){toast('Reconcile failed',error.message,'error');}
      finally{if(button)button.disabled=false;}
    });
    win.querySelector('[data-runeschema-load-order-list]')?.addEventListener('click',(event)=>{
      const upButton=event.target.closest('[data-runeschema-load-order-up]'),downButton=event.target.closest('[data-runeschema-load-order-down]');
      if(!upButton&&!downButton)return;
      const index=Number((upButton||downButton).dataset.index);
      if(!runeschemaLoadOrderEntries||Number.isNaN(index))return;
      const swapWith=upButton?index-1:index+1;
      if(swapWith<0||swapWith>=runeschemaLoadOrderEntries.length)return;
      const entries=runeschemaLoadOrderEntries.slice();
      [entries[index],entries[swapWith]]=[entries[swapWith],entries[index]];
      const path=win.querySelector('[data-runeschema-load-order-path]')?.title;
      paintRuneschemaLoadOrder({entries,mods_path:path,note:'Unsaved reordering.'});
      const save=win.querySelector('[data-runeschema-load-order-save]');
      if(save)save.disabled=false;
    });
    win.querySelector('[data-runeschema-load-order-list]')?.addEventListener('change',(event)=>{
      const checkbox=event.target.closest('[data-runeschema-load-order-enabled]');
      if(!checkbox||!runeschemaLoadOrderEntries)return;
      const index=Number(checkbox.dataset.index);
      if(Number.isNaN(index)||!runeschemaLoadOrderEntries[index])return;
      runeschemaLoadOrderEntries[index].enabled=checkbox.checked;
      const save=win.querySelector('[data-runeschema-load-order-save]');
      if(save)save.disabled=false;
    });
    win.querySelector('[data-runeschema-load-order-save]')?.addEventListener('click',async()=>{
      const save=win.querySelector('[data-runeschema-load-order-save]');
      if(!runeschemaLoadOrderEntries||!save)return;
      save.disabled=true;
      try{const payload=await api.invoke('server.console.runeschema.load_order.write',{id:world.id,entries:runeschemaLoadOrderEntries});paintRuneschemaLoadOrder({entries:payload?.entries||runeschemaLoadOrderEntries,mods_path:payload?.mods_path,note:'Saved.'});toast('Load order saved',payload?.mods_path||'mods.txt','success');}
      catch(error){toast('Load order not saved',error.message,'error');save.disabled=false;}
    });
    win.querySelector('[data-runeschema-compatibility-generate]')?.addEventListener('click',async()=>{
      const button=win.querySelector('[data-runeschema-compatibility-generate]'),output=win.querySelector('[data-runeschema-compatibility-output]'),note=win.querySelector('[data-runeschema-compatibility-note]');
      if(button)button.disabled=true;
      try{
        const payload=await api.invoke('server.console.runeschema.compatibility.generate',{id:world.id});
        if(output){output.hidden=false;output.textContent=payload?.report||'';}
        if(note)note.textContent=payload?.warning_count?`${payload.warning_count} potential conflict${payload.warning_count===1?'':'s'} found.${payload.path?` Written to ${payload.path}.`:''}`:'No cross-mod conflicts found.';
      }catch(error){if(note)note.textContent=error.message;toast('Compatibility report failed',error.message,'error');}
      finally{if(button)button.disabled=false;}
    });
    win.querySelector('[data-runeschema-fmodel-generate]')?.addEventListener('click',async()=>{
      const button=win.querySelector('[data-runeschema-fmodel-generate]'),output=win.querySelector('[data-runeschema-fmodel-output]'),note=win.querySelector('[data-runeschema-fmodel-note]');
      if(button)button.disabled=true;
      try{
        const payload=await api.invoke('server.console.runeschema.fmodel.generate',{id:world.id});
        if(output){output.hidden=false;output.textContent=`Generated ${payload?.generated||0} snippet${payload?.generated===1?'':'s'}${(payload?.skipped||[]).length?` (skipped: ${payload.skipped.join(', ')})`:''} from ${payload?.input_path||'fmodel-input'} to ${payload?.output_path||'fmodel-snippets'}.`;}
        if(note)note.textContent=payload?.generated?'Done.':'No recognizable FModel exports found in fmodel-input.';
      }catch(error){if(note)note.textContent=error.message;toast('FModel snippet generation failed',error.message,'error');}
      finally{if(button)button.disabled=false;}
    });
    win.querySelectorAll('[data-runeschema-subtab]').forEach((button,index)=>{button.setAttribute('role','tab');button.setAttribute('aria-selected',String(index===0));button.addEventListener('click',()=>{
      const selected=button.dataset.runeschemaSubtab||'overview';
      win.querySelectorAll('[data-runeschema-subtab]').forEach((item)=>{const active=item===button;item.classList.toggle('primary',active);item.classList.toggle('ghost',!active);item.setAttribute('aria-selected',String(active));});
      win.querySelectorAll('[data-runeschema-subpanel]').forEach((panel)=>{panel.hidden=panel.dataset.runeschemaSubpanel!==selected;});
      if(selected==='loadorder'&&!runeschemaLoadOrderEntries)loadRuneschemaLoadOrder();
    });});
    let nativePolicy=null;
    const paintNativePolicy=()=>{const enabled=!!nativePolicy?.native_consoles_enabled;win.querySelectorAll('[data-native-console-toggle]').forEach((button)=>{button.textContent=enabled?'Use Sync as sole console next launch':'Show original consoles next launch';button.classList.toggle('danger',enabled);button.classList.toggle('primary',!enabled);button.classList.remove('ghost');});const status=win.querySelector('[data-native-console-status]');if(status){status.textContent=enabled?'NATIVE FALLBACK ON':'SYNC ONLY';status.className=`status-pill ${enabled?'unknown':'online'}`;}const note=win.querySelector('[data-native-console-note]');if(note)note.textContent=nativePolicy?.next_launch_required?'Saved. Restart this World to apply.':(nativePolicy?.reason||'Policy is ready for the next launch.');const path=win.querySelector('[data-native-console-path]');if(path){path.textContent=nativePolicy?.settings_path||'UE4SS settings will be created during runtime setup.';path.title=nativePolicy?.settings_path||'';}};
    const refreshNativePolicy=async()=>{try{const response=await api.invoke('server.console.policy',{id:world.id});nativePolicy=response?.policy||{};paintNativePolicy();}catch(error){nativePolicy={};const note=win.querySelector('[data-native-console-note]');if(note)note.textContent=error.message;}};
    win.querySelectorAll('[data-native-console-toggle]').forEach((button)=>button.addEventListener('click',async()=>{button.disabled=true;try{const response=await api.invoke('server.console.policy',{id:world.id,native_consoles_enabled:!nativePolicy?.native_consoles_enabled});if(response?.state)setData(response.state);nativePolicy=response?.policy||{};paintNativePolicy();toast('Runtime console policy saved',nativePolicy.reason||'The change applies on the next server launch.','success');}catch(error){toast('Console policy failed',error.message,'error');}finally{button.disabled=false;}}));
    win.querySelectorAll('[data-runtime-tool-command]').forEach((button)=>button.addEventListener('click',async()=>{const command=button.dataset.runtimeToolCommand||'';if(!command||!await managedConfirm(`Run this runtime dumper?\n\n${command}`,'Confirm Runtime Dumper'))return;button.disabled=true;try{const result=await api.invoke('server.console.execute',{id:world.id,command,confirmed:true,source:'desktop-runtime-tools',actor:'owner'});toast('Runtime dumper acknowledged',result?.ack||command,'success');await refresh();}catch(error){toast('Runtime dumper failed',error.message,'error');}finally{button.disabled=false;}}));
    win.querySelector('[data-open-runeschema-configuration]')?.addEventListener('click',()=>{state.selectedServerWorldId=world.id;state.route='server-detail';state.serverTab='configuration';render();});
    // Keep the application console genuinely live while preserving one bounded
    // in-flight IPC read.  refresh() refuses overlap, draw() skips unchanged
    // payloads, and the recursive timeout schedules only after the prior read
    // completes, so a slow worker can never accumulate an IPC polling backlog.
    let timer=null;const schedule=()=>{if(disposed||!win.isConnected){disposed=true;return;}timer=setTimeout(async()=>{await refresh();schedule();},document.hidden?5000:1000);};
    win._dwsDispose=()=>{disposed=true;if(timer)clearTimeout(timer);};refresh().finally(schedule);
    refreshNativePolicy();
    return win;
  }

  function launchRuntimeConsoleForWorld(world) {
    if (!world?.id) return null;
    // Runtime output is collected by the backend whether or not its view is
    // mounted. Starting/restarting a World must never steal focus, navigate to
    // Console, or create another renderer. Opening or detaching the console is
    // an explicit operator action.
    state.selectedServerWorldId=world.id;
    if(state.data?.application?.background_mode?.open_sync_console_on_host_start===true){
      return openUnifiedLaunchConsole(world);
    }
    return null;
  }

  async function runServerStartOperation(world, task) {
    if(state.operation)throw new Error(`${state.operation.title} is already in progress.`);
    const stages=[['applying','Applying profile mods and settings…',12],['game','Starting the dedicated game process…',34],['bridge','Waiting for the DragonLink game bridge…',56],['multiplayer','Starting the multiplayer broadcast…',76],['sync','Starting the continuous Sync broadcast…',90],['ready','Server and broadcasts are ready.',100]];
    state.operation={title:`Starting ${world?.name||'hosted World'}`,detail:stages[0][1],phase:stages[0][0],percent:stages[0][2],phases:stages.map((row)=>row[0]),position:{x:0,y:0}};render();
    let index=0;const timer=setInterval(()=>{if(!state.operation||index>=stages.length-2)return;index+=1;const [phase,detail,percent]=stages[index];Object.assign(state.operation,{phase,detail,percent});const banner=root.querySelector('.operation-banner');if(!banner)return;banner.querySelector('[data-operation-detail]').textContent=detail;banner.querySelector('[data-operation-progress]').style.width=`${percent}%`;banner.querySelector('[data-operation-percent]').textContent=`${percent}%`;banner.querySelectorAll('[data-operation-phase]').forEach((node,nodeIndex)=>{node.classList.toggle('complete',nodeIndex<index);node.classList.toggle('active',nodeIndex===index);});},1400);
    try{const response=await task();index=stages.length-1;Object.assign(state.operation,{phase:'ready',detail:stages[index][1],percent:100});return response;}
    finally{clearInterval(timer);state.operation=null;render();}
  }

  function startPlayerPolling(world = activeServerWorld()) {
    stopPlayerPolling();
    if (!world) return;
    const worldId=String(world.id||'');
    const resolve=()=>privateWorldById(worldId) || serverWorlds().find(w=>String(w.id)===worldId) || world;
    refreshServerPlayers(resolve(), true, true);
    // The backend owns a cached RSDWTools roster lease. Refreshing the view at
    // the same cadence avoids redundant IPC/render work and UE4SS console spam.
    state.playerPollTimer = setInterval(() => { if (backgroundRefreshAllowed()) refreshServerPlayers(resolve(), true, true); }, 15000);
  }

  async function ensureAshenfallMap({force=false, world=null} = {}) {
    try {
      let status = await api.invoke('application.map.status', {});
      if (force || !status?.data_url) status = await api.invoke('application.map.refresh', { force });
      state.mapCacheStatus = status || null;
      if (!state.mapOverlays) {
        try { const overlays=await api.invoke('application.map.overlays', {});state.mapOverlays={...(overlays||{}),points:objectRows(overlays?.points),categories:overlays?.categories&&typeof overlays.categories==='object'?overlays.categories:{}}; } catch (_) { state.mapOverlays = { points: [], categories: {} }; }
      }
      if (world && status?.data_url) {
        const isPrivate = world.kind === 'singleplayer' || !!privateWorldById(world.id);
        const existing = state.serverMapConfig[world.id] || world.player_map || {};
        if (!existing.background_data || force) {
          const calibration = state.mapOverlays?.calibration || existing.calibration || {};
          const coordinate_source=state.mapOverlays?.coordinate_source||status.coordinate_source||'';
          const params = isPrivate ? { profile_id: world.id, background_data: status.data_url, calibration, coordinate_source } : { id: world.id, background_data: status.data_url, calibration, coordinate_source };
          const response = await api.invoke(isPrivate ? 'singleplayer.map.update' : 'server.world.map.update', params);
          state.serverMapConfig[world.id] = response.player_map || { ...existing, background_data: status.data_url };
          if (response.state) state.data = response.state;
        }
      }
      return status;
    } catch (error) {
      console.warn('Ashenfall map refresh unavailable:', error);
      return null;
    }
  }

  async function loadServerTabData(tab) {
    state.serverTab = tab;
    if (!['players','map'].includes(tab)) stopPlayerPolling();
    // Navigation is visual state, so paint it immediately. Disk scans and
    // bridge calls complete behind the selected tab instead of making the
    // interface appear frozen.
    render();
    const world = activeServerWorld();
    if (!world) return;
    const cacheKey = `${world.id}:${tab}`;
    const ttl = ['players','map'].includes(tab) ? 4000 : ['overview','activity'].includes(tab) ? 10000 : 30000;
    if (state.serverTabLoading[cacheKey]) return state.serverTabLoading[cacheKey];
    if (Date.now() - Number(state.serverTabLoadedAt[cacheKey] || 0) < ttl) {
      if (['players','map'].includes(tab)) startPlayerPolling(world);
      return;
    }
    const load = (async () => {
      if (tab === 'players' || tab === 'map') {
        await refreshServerPlayers(world, true, false);
        if(tab==='players') await refreshStarterCharacters(world, true);
        if(tab==='map') await ensureAshenfallMap({ world });
        render(); startPlayerPolling(world); return;
      }
      if (tab === 'spawner') { await refreshServerPlayers(world, true, false); await refreshServerSpawner(world, { quiet:true }); return; }
      if (tab === 'console') { await refreshServerConsole(world, true); return; }
      if (tab === 'mods') { await refreshServerInventory(world, true); return; }
      if (tab === 'backups') { await refreshServerBackups(world, true); return; }
      if (tab === 'feedback') { await refreshServerFeedback(world, true); return; }
      if (tab === 'maintenance' || tab === 'configuration') { await refreshServerRuntime(true); await refreshWorldMaintenance(world, true); return; }
      if (tab === 'save-editor') { await refreshWorldSaveEditor(world, 'server', true); return; }
      if (['overview','activity'].includes(tab)) { await refreshServerRuntime(true); return; }
    })();
    state.serverTabLoading[cacheKey] = load;
    try { await load; state.serverTabLoadedAt[cacheKey] = Date.now(); }
    finally { delete state.serverTabLoading[cacheKey]; }
  }

  async function loadPrivateTabData(tab) {
    state.privateTab = tab;
    if (!['players','map'].includes(tab)) stopPlayerPolling();
    const world = privateWorldById(state.selectedWorldId) || singleplayerWorld();
    render();
    if (!world) return;
    state.data.client.active_private_world_id = world.id;
    const cacheKey=`${world.id}:${tab}`;
    const ttl=['players','map'].includes(tab)?4000:['overview','activity'].includes(tab)?5000:20000;
    if(state.privateTabLoading[cacheKey])return state.privateTabLoading[cacheKey];
    if(Date.now()-Number(state.privateTabLoadedAt[cacheKey]||0)<ttl){if(['players','map'].includes(tab))startPlayerPolling(world);return;}
    const load=(async()=>{
      if (tab === 'players' || tab === 'map') {
        await refreshServerPlayers(world, true, false);
        if (tab === 'map') await ensureAshenfallMap({ world });
        render(); startPlayerPolling(world); return;
      }
      if (tab === 'mods') { await refreshSinglePlayerInventory(true); return; }
      if (tab === 'configuration') {
        try { const response=await api.invoke('singleplayer.config.list',{profile_id:world.id});state.singleplayerConfigs[world.id]=response.configs||[]; }
        catch (_) { state.singleplayerConfigs[world.id]=[]; }
        render(); return;
      }
      if (tab === 'save-editor') { await refreshWorldSaveEditor(world, 'private', true); return; }
      if (tab === 'networking' || !state.privateProfileDetails[world.id]) {
        try { const response=await api.invoke('singleplayer.profile.get',{profile_id:world.id});state.privateProfileDetails[world.id]=response.profile||{};if(response.state)state.data=response.state; } catch (_) {}
      }
      if (['overview','maintenance'].includes(tab)) { await refreshServerRuntime(true); return; }
      render();
    })();
    state.privateTabLoading[cacheKey]=load;
    try{await load;state.privateTabLoadedAt[cacheKey]=Date.now();}
    finally{delete state.privateTabLoading[cacheKey];}
  }

  function setupCheckRows(validation) {
    if (!validation?.checks?.length) return '<div class="empty-state compact">Choose a path, then validate it.</div>';
    return `<div class="setup-checks">${validation.checks.map((c) => `<div class="setup-check ${c.exists ? 'ok' : (c.optional ? 'optional' : 'bad')}"><span>${c.exists ? '✓' : (c.optional ? '○' : '×')}</span><div><strong>${escapeHtml(c.kind)}</strong><small title="${escapeHtml(c.path)}">${escapeHtml(c.path)}</small></div></div>`).join('')}</div>`;
  }

  async function offerExistingServerModImport(path, { importNow = false } = {}) {
    const detected=await api.invoke('server.install.detect_mods',{path});
    if(!detected?.detected)return {detected:false,accepted:false,result:null};
    const preview=(detected.mods||[]).slice(0,12).map((mod)=>`${mod.type} · ${mod.name} (${mod.files} file${mod.files===1?'':'s'})`).join('\n');
    const accepted=await managedConfirm(`Mods Detected in Directory! Do you wish to place them in this World Profile?\n\n${preview}${detected.count>12?`\n…and ${detected.count-12} more`:''}\n\nImporting copies these mods into the selected World Profile before the live server directory is changed.`,'Existing Server Mods Detected');
    if(!accepted||!importNow)return {detected:true,accepted,result:null};
    const result=await api.invoke('server.install.import_mods',{path});
    if(result.state)setData(result.state);
    toast('Server mods imported',`${result.count||0} mod group(s) · ${result.files_captured||0} file(s) placed in this World Profile.`,'success');
    return {detected:true,accepted:true,result};
  }

  function openGuidedSetup(mode='player', options={}) {
    state.setupMode = mode === 'server' ? 'server' : 'player';
    const server = state.setupMode === 'server';
    const a = state.data?.application || {};
    const install = a.server_install || {};
    const initialPath = server ? (install.install_dir || '') : (a.game_dir || '');
    const owner = server ? (install.owner_id || '') : '';
    const clientNodes = [
      ['1','Find Dragonwilds','Locate the local game and SaveCharacters folder.'],
      ['2','Characters','Discover real saves, portraits, and World assignments.'],
      ['3','SinglePlayer','Build the local default World, mods, map, and character.'],
      ['4','LAN Worlds','Discover trusted same-home Worlds and add placards.'],
      ['5','Safety','Check Direct Connect, runtime validation, and RSDW cache.'],
      ['6','Ready','Launch the selected local or hosted World.'],
    ];
    const serverNodes = [
      ['1','Server Files','Adopt or install the dedicated-server tree.'],
      ['2','Player ID','Save OwnerId/OwnerID in DedicatedServer.ini.'],
      ['3','UE4SS','Install/update the server runtime from URL or ZIP.'],
      ['4','RuneSchema','Install the baked core or configured update source.'],
      ['5','Network','Configure firewall, ports, schedules, and publish state.'],
    ];
    const nodes = server ? serverNodes : clientNodes;
    showModal(`<div class="modal-header"><div><div class="eyebrow">${server ? 'Server Guided Startup' : 'Client Guided Startup'}</div><h2>${server ? 'Build a Dedicated World Host' : 'Prepare Your Dragonwilds Launcher'}</h2><p>${server ? 'Server setup shares the same visual language as Client setup, but performs a different deployment flow.' : 'A polished local-first setup for characters, SinglePlayer, LAN discovery, and normal hosted Worlds.'}</p></div><button class="modal-close" data-close-modal>×</button></div>
      <div class="modal-body guided-setup-body"><div class="guided-flow">
        <div class="guided-flow-hero ${server ? 'server' : ''}"><div><div class="eyebrow">${server ? 'HOST' : 'PLAY'}</div><h3>${server ? 'One server install. Many World profiles.' : 'One launcher. Your local and multiplayer Worlds.'}</h3><p>${server ? 'Dragonwilds Sync installs the shared runtimes once, then World placards own their mods, configs, schedules, characters, and presentation.' : 'Client setup links the game, discovers characters, prepares the SinglePlayer profile, and gets LAN/remote World launching ready without exposing unnecessary server controls.'}</p></div></div>
        <div class="flow-track">${nodes.map(([n,title,copy],i)=>`<div class="flow-node ${i===0?'current':''}"><small>${n}</small><strong>${escapeHtml(title)}</strong><span>${escapeHtml(copy)}</span></div>`).join('')}</div>
        <section class="panel"><div class="panel-header"><div><h2>${server ? 'Server Location & Identity' : 'Dragonwilds Installation'}</h2><span class="panel-subtitle">${server ? 'This becomes the shared machine-level host installation.' : 'Your saves, client mods, and local SinglePlayer profile resolve from here.'}</span></div></div><div class="panel-body">
          <div class="path-field"><input class="field" id="guided-setup-path" value="${escapeHtml(initialPath)}" placeholder="${server ? 'C:\\DragonwildsServer' : 'D:\\SteamLibrary\\steamapps\\common\\RSDragonwilds'}"/><button class="btn ghost" id="guided-browse">Browse</button><button class="btn primary" id="guided-validate">Validate</button></div>
          ${server ? `<div class="setup-owner-box"><label>Dragonwilds Player ID / Owner ID</label><div class="path-field"><input class="field" id="guided-owner-id" value="${escapeHtml(owner)}" placeholder="Copy from Dragonwilds → Settings"/><button class="btn ghost" id="guided-detect-owner">Detect from Game</button></div><small>Saved to <code>DedicatedServer.ini</code>. SteamCMD uses anonymous login.</small></div>` : `<div class="identity-box steam-cloud-action" data-open-steam-cloud-settings role="button" tabindex="0"><strong>Character-aware setup</strong><p>After the path validates, Dragonwilds Sync reads SaveCharacters, creates the SinglePlayer placard, and keeps character switching/backups in APPDATA. Steam Cloud should be disabled when dynamic character profiles are used.</p><button type="button" class="btn ghost compact-btn">Open Steam Cloud Settings</button></div>`}
          <div id="guided-validation">${setupCheckRows(null)}</div>
        </div></section>
        <section class="setup-network"><div><strong>${server ? 'Deployment connectivity' : 'Connection readiness'}</strong><span>${server ? 'Checks outbound access needed for server/runtime updates. Firewall configuration is handled during Full Setup.' : 'Checks outbound access before LAN discovery and World synchronization.'}</span></div><button class="btn ghost" id="guided-network-test">Test Connection</button></section><div id="guided-network-result"></div>
        ${server ? `<label class="inline-check setup-install-check"><input type="checkbox" id="guided-install-now" checked/> Run Full Setup after saving: dedicated server → UE4SS → RuneSchema → DedicatedServer.ini → firewall</label>` : ''}
      </div></div>
      <div class="modal-footer"><button class="btn ghost" id="guided-skip">${options.serverEnable ? 'Skip for now' : 'Skip Setup'}</button><div class="footer-right"><button class="btn ghost" data-close-modal>Cancel</button><button class="btn primary" id="guided-complete">${server ? 'Save & Prepare Server' : 'Save Client Setup'}</button></div></div>`);
    modalRoot.querySelector('.modal')?.classList.add('setup-modal');
    modalRoot.querySelector('[data-open-steam-cloud-settings]')?.addEventListener('click', openSteamCloudSettings);
    modalRoot.querySelector('[data-open-steam-cloud-settings]')?.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); openSteamCloudSettings(); }
    });
    let validation = null;
    const validate = async () => {
      const path = modalRoot.querySelector('#guided-setup-path')?.value.trim() || '';
      try { validation = await api.invoke(server ? 'setup.validate_server' : 'setup.validate_client', { path, allow_new:true }); modalRoot.querySelector('#guided-validation').innerHTML = setupCheckRows(validation); return validation; }
      catch (error) { toast('Path validation failed', error.message, 'error'); return null; }
    };
    modalRoot.querySelector('#guided-browse')?.addEventListener('click', async () => { const value=await window.dragonwilds.pickDirectory(); if(value){ modalRoot.querySelector('#guided-setup-path').value=value; await validate(); }});
    modalRoot.querySelector('#guided-validate')?.addEventListener('click', validate);
    modalRoot.querySelector('#guided-network-test')?.addEventListener('click', async () => {
      const out=modalRoot.querySelector('#guided-network-result'); out.innerHTML='<div class="muted-small">Testing…</div>';
      try { const r=await api.invoke('setup.network_probe',{}); out.innerHTML=`<div class="identity-box compact-box"><strong>${r.ok ? 'Reachable' : 'Unavailable'}</strong><p>${escapeHtml(r.message)}${r.best_latency_ms != null ? ` Best TCP handshake: ${escapeHtml(String(r.best_latency_ms))} ms.` : ''}</p></div>`; }
      catch(error){ out.innerHTML=`<div class="warning-box">${escapeHtml(error.message)}</div>`; }
    });
    modalRoot.querySelector('#guided-detect-owner')?.addEventListener('click', async () => {
      try { const result=await api.invoke('setup.owner_id.detect',{}); if(!result.ok)throw new Error(result.error||'Player ID was not found.'); modalRoot.querySelector('#guided-owner-id').value=result.owner_id; toast('Player ID detected', `${result.masked} · ${result.source}`, 'success'); }
      catch(error){toast('Player ID not detected',error.message,'error');}
    });
    modalRoot.querySelector('#guided-skip')?.addEventListener('click', async () => { try { await api.invoke('setup.skip',{mode:state.setupMode}); if(options.serverEnable) await updateApplication({server_mode_enabled:true}); closeModal(); } catch(error){toast('Could not skip setup',error.message,'error');} });
    modalRoot.querySelector('#guided-complete')?.addEventListener('click', async () => {
      const v = validation || await validate(); if(!v?.ok) return toast('Path needs attention', v?.message || 'Validate the selected path first.', 'error');
      const path=modalRoot.querySelector('#guided-setup-path')?.value.trim()||''; const ownerId=modalRoot.querySelector('#guided-owner-id')?.value.trim()||'';
      try {
        let importExistingMods=true;
        if(server&&v.mode==='existing')importExistingMods=(await offerExistingServerModImport(path)).accepted;
        const next=await api.invoke('setup.complete',{mode:state.setupMode,path,owner_id:ownerId,import_existing_mods:importExistingMods}); setData(next);
        if(server && v.mode==='build' && modalRoot.querySelector('#guided-install-now')?.checked){ toast('Installing dedicated server','SteamCMD is downloading/validating the free dedicated server.'); const result=await api.invoke('server.install.full_setup',{}); if(result.state)setData(result.state); }
        closeModal(); toast('Guided setup complete', server ? 'Dedicated server paths and Owner ID are saved.' : 'Dragonwilds client paths are saved.', 'success');
      } catch(error){ toast('Setup could not finish',error.message,'error'); }
    });
    setTimeout(validate,0);
  }

  function openWebHostSetup({ enableFeature = true } = {}) {
    const cfg=state.data?.application?.world_directory_host||{};
    const remote=cfg.remote_admin||{};
    showModal(`<div class="modal-header"><div><div class="eyebrow">WebHost Guided Setup</div><h2>Publish a Safe Dragonwilds Directory</h2><p>WebHost is independent from every game-server process. This walkthrough chooses the public surface, listener, firewall, and initial remote authority.</p></div><button class="modal-close" data-close-modal>×</button></div><div class="modal-body guided-setup-body"><div class="flow-track"><div class="flow-node current"><small>1</small><strong>Surface</strong><span>Website, manifest-only, or blackout.</span></div><div class="flow-node"><small>2</small><strong>Listener</strong><span>Local TCP port and optional public DNS.</span></div><div class="flow-node"><small>3</small><strong>Firewall</strong><span>Windows rule and router/tunnel choice.</span></div><div class="flow-node"><small>4</small><strong>Verify</strong><span>Local, LAN, then external test.</span></div></div><section class="panel"><div class="panel-body form-grid">
      <div class="form-group"><label>Public browser surface</label><select class="select" id="guided-webhost-surface"><option value="full" ${(cfg.public_surface_mode||'full')==='full'?'selected':''}>Full joinable-World directory</option><option value="manifest" ${cfg.public_surface_mode==='manifest'?'selected':''}>Manifest only · icon landing</option><option value="blackout" ${cfg.public_surface_mode==='blackout'?'selected':''}>Total blackout · blank browser</option></select><small>This controls the WebHost directory only. Remote Server Admin is a separate surface.</small></div>
      <div class="form-group"><label>Website TCP port</label><input class="field" id="guided-webhost-port" type="number" min="1" max="65535" value="${escapeHtml(cfg.port||27080)}"/></div>
      <div class="form-group full"><label>WebHost publishing</label><select class="select" id="guided-webhost-publication-mode"><option value="local" ${(cfg.publication_mode||'manual')==='local'?'selected':''}>Local network only</option><option value="manual" ${(cfg.publication_mode||'manual')==='manual'?'selected':''}>Manual router forwarding</option><option value="upnp" ${cfg.publication_mode==='upnp'?'selected':''}>Automatic UPnP · verify before public</option><option value="tunnel" ${cfg.publication_mode==='tunnel'?'selected':''}>Cloudflare Tunnel · WebHost only</option></select><small>Only one mode is active. Cloudflare is outbound-only and never changes gameplay or World Sync.</small></div>
      <div class="form-group full"><label>Public DNS / HTTPS URL (optional)</label><input class="field" id="guided-webhost-url" value="${escapeHtml(cfg.public_base_url||'')}" placeholder="https://worlds.example.com"/></div>
      <label class="checkbox-row"><input id="guided-webhost-firewall" type="checkbox" checked/> Repair the application-owned firewall rule (elevation requested for this step only)</label>
      <label class="checkbox-row full"><input id="guided-webhost-start" type="checkbox"/> Start the WebHost listener after saving</label>
    </div></section><div class="webhost-port-matrix"><div><strong>WebHost / Remote Server</strong><code>TCP ${escapeHtml(String(cfg.port||27080))}</code><span>Windows firewall + router forward, unless an outbound HTTPS tunnel is used.</span></div><div><strong>Dragonwilds gameplay</strong><code>UDP 7777 + instance</code><span>Dedicated server firewall + router forward. Separate from WebHost.</span></div><div><strong>World Sync</strong><code>TCP profile Sync port</code><span>Required only when remote clients connect directly to the launcher fingerprint/sync service.</span></div></div><div class="identity-box"><strong>Public verification is a separate step</strong><p>A DNS value or detected WAN IP is only an address candidate. After the listener starts, test locally and on LAN, then confirm from cellular or another external network because many routers do not support NAT hairpin tests.</p></div></div><div class="modal-footer"><button class="btn ghost" id="guided-webhost-skip">Enable Workspace Only</button><div class="footer-right"><button class="btn ghost" data-close-modal>Cancel</button><button class="btn primary" id="guided-webhost-complete">Save WebHost Setup</button></div></div>`);
    modalRoot.querySelector('.modal')?.classList.add('setup-modal');
    modalRoot.querySelector('#guided-webhost-skip')?.addEventListener('click',async()=>{try{state.data=await api.invoke('application.advanced.settings',{webhost_enabled:true});closeModal();state.route='webhost';state.webhostTab='settings';render();toast('WebHost workspace enabled','The listener remains off until you enable it.','success');}catch(error){toast('WebHost setup failed',error.message,'error');}});
    modalRoot.querySelector('#guided-webhost-complete')?.addEventListener('click',async()=>{try{const enabled=!!modalRoot.querySelector('#guided-webhost-start')?.checked;const surface=modalRoot.querySelector('#guided-webhost-surface')?.value||'full';const publicationMode=modalRoot.querySelector('#guided-webhost-publication-mode')?.value||'manual';const next={...cfg,enabled,directory_enabled:true,port:Number(modalRoot.querySelector('#guided-webhost-port')?.value||27080),public_base_url:modalRoot.querySelector('#guided-webhost-url')?.value.trim()||'',publication_mode:publicationMode,upnp_enabled:publicationMode==='upnp',public_transport:publicationMode==='tunnel'?'cloudflare_quick':'direct',public_surface_mode:surface,remote_admin:{...remote}};state.data=await api.invoke('application.advanced.settings',{webhost_enabled:true});const response=await api.invoke('application.world_directory_host.settings',next);if(response.state)state.data=response.state;if(modalRoot.querySelector('#guided-webhost-firewall')?.checked&&enabled&&!['tunnel','none'].includes(publicationMode))await api.invoke('application.world_directory_host.firewall',{});closeModal();state.route='webhost';state.webhostTab=enabled?'live':'settings';render();toast('WebHost setup saved',enabled?(publicationMode==='tunnel'?'The local listener is online and the temporary HTTPS address is being created.':'The listener is online. Run external verification before sharing it.'):'The workspace is ready; the listener remains off.','success');}catch(error){toast('WebHost setup failed',error.message,'error');}});
  }

  async function checkApplicationUpdate(manual = false) {
    const cfg = state.data?.application?.application_updates || {};
    const repositoryUrl = 'https://github.com/gh0sted5456-us/Dragonwilds-Sync';
    try {
      let result = await window.dragonwilds.appUpdateCheck({ repositoryUrl, etag: cfg.etag || '' });
      if (result.notModified && (manual || (cfg.last_available_version && cfg.dismissed_version !== cfg.last_available_version))) {
        result = await window.dragonwilds.appUpdateCheck({ repositoryUrl, etag: '' });
      }
      if (result.notModified) {
        if (manual) toast('Application is current', 'GitHub reports no release metadata changes.', 'success');
        return result;
      }
      state.applicationUpdate = result;
      const updatedCfg = { ...cfg, github_url: repositoryUrl, etag: result.etag || '', last_checked_at: new Date().toISOString(), last_available_version: result.latestVersion || '', last_error: '' };
      state.data = await api.invoke('application.update', { application_updates: updatedCfg });
      state.data = await api.invoke('application.update_status.record', {
        installed_version: window.DWSYNC_RELEASE_META?.version || '', available_version: result.latestVersion || result.tag || '',
        update_available: !!result.available, restart_required: !!result.available,
        status: result.available ? 'update_available' : 'current', checked_at: Date.now()/1000,
        action: result.available ? 'Use Update Application in the desktop launcher' : 'No action required'
      });
      if (manual) toast(result.available ? 'Application update available' : 'Application is current', result.available ? `${result.name || result.tag} is ready.` : `Release ${result.latestVersion || '—'} is not newer than this build.`, result.available ? '' : 'success');
      render();
      return result;
    } catch (error) {
      const updatedCfg = { ...cfg, last_checked_at: new Date().toISOString(), last_error: error.message };
      try { state.data = await api.invoke('application.update', { application_updates: updatedCfg }); } catch (_) {}
      try { state.data = await api.invoke('application.update_status.record', {installed_version:window.DWSYNC_RELEASE_META?.version||'',update_available:false,restart_required:false,status:'unable_to_check',checked_at:Date.now()/1000,action:'Retry from the desktop launcher',last_error:error.message}); } catch (_) {}
      if (manual) toast('Application update check failed', error.message, 'error');
      return null;
    }
  }

  async function applyApplicationUpdate(release = state.applicationUpdate) {
    const cfg = state.data?.application?.application_updates || {};
    if (!release?.available) return toast('No application update selected', 'Check GitHub for an update first.', 'error');
    if (!release.asset) return toast('Release asset missing', 'Publish the Portable Windows EXE asset on the GitHub Release.', 'error');
    try {
      toast('Downloading application update', `${release.asset.name} · SHA-256 will be verified before replacement.`);
      await window.dragonwilds.appUpdateApply({ repositoryUrl: 'https://github.com/gh0sted5456-us/Dragonwilds-Sync', release });
      try { state.data=await api.invoke('application.update_status.record',{installed_version:window.DWSYNC_RELEASE_META?.version||'',available_version:release.latestVersion||release.tag||'',update_available:true,restart_required:true,status:'staged',checked_at:Date.now()/1000,action:'Restart the launcher to apply the staged update'}); } catch (_) {}
      toast('Update staged', 'Dragonwilds Sync will close, replace the portable application, and relaunch.', 'success');
    } catch (error) { toast('Application update blocked', error.message, 'error'); }
  }

  async function openDirectoryJoin(request) {
    if (!request?.directoryUrl || !request?.worldId) return;
    if (!state.data) { state.pendingDirectoryJoin=request; return; }
    state.pendingDirectoryJoin=null;
    try {
      const inspected=await api.invoke('world.directory.join.inspect',{directory_url:request.directoryUrl,world_id:request.worldId});
      const world=inspected.world||{},identity=world.identity||{},presentation=world.presentation||{},connection=world.connection||{},status=world.status||{};
      state.entered=true;
      showModal(`<div class="modal-header"><div><div class="eyebrow">Verified WebHost Handoff</div><h2>Link ${escapeHtml(identity.world_name||'Dragonwilds World')}</h2><p>The directory supplies discovery metadata only. Dragonwilds Sync independently verifies the live fingerprint before downloading or applying files.</p></div><button class="modal-close" data-close-modal>×</button></div><div class="modal-body"><div class="identity-box"><strong>World Name · ${escapeHtml(identity.world_name||'World')}</strong><p>${escapeHtml(presentation.description||'Sync-ready Dragonwilds World')}</p></div><div class="health-evidence-grid">${metric('Region',status.region||status.country_name||'Unknown')}${metric('Players',`${status.player_count||0}${status.player_capacity?` / ${status.player_capacity}`:''}`)}${metric('External route',connection.external_ip?`${connection.external_ip}:${connection.game_port||7777}`:'Not published')}${metric('Fingerprint','Live verification required')}</div><div class="form-grid" style="margin-top:16px"><label><small>World Password</small><input class="field" id="directory-join-password" type="password" autocomplete="off" placeholder="Leave blank for an open World"></label></div><div class="identity-box"><strong>Simple connection contract</strong><p>World Name identifies the World and the optional World Password authorizes launcher synchronization.</p></div></div><div class="modal-footer"><button class="btn ghost" data-close-modal>Cancel</button><div class="footer-right"><button class="btn ghost" id="directory-save-link">Save Link</button><button class="btn primary" id="directory-link-play">Link &amp; Sync</button></div></div>`,{title:'Link Dragonwilds World',width:900,height:700});
      const complete=async(sync)=>{
        const password=modalRoot.querySelector('#directory-join-password')?.value||'';
        let linkedWorld=null;
        try {
          const outcome=await runOperation('Linking World','Saving the directory identity and requiring live fingerprint verification before any files are applied…',async()=>{
            const linked=await api.invoke('world.directory.join.link',{directory_url:request.directoryUrl,world_id:request.worldId,password});
            const worldId=linked.world?.id||linked.state?.client?.active_world_id||state.data?.client?.active_world_id||null;
            if(!worldId)throw new Error('The linked World did not return a stable profile ID.');
            if(linked.state)setData(linked.state);
            return {linked,worldId};
          });
          linkedWorld=worlds().find((item)=>item.id===outcome.worldId)||outcome.linked.world||{id:outcome.worldId};
          const synced=sync?await runWorldSyncJob(linkedWorld,'sync'):null;
          if(synced?.state)setData(synced.state);else if(outcome.linked.state)setData(outcome.linked.state);
          state.selectedWorldId=outcome.worldId;
          closeModal();state.route='world-detail';render();
          if(sync){
            openVerifiedPlayGate(worlds().find((item)=>item.id===outcome.worldId)||linkedWorld,synced);
            toast('Sync complete','File parity is verified. Launch only when you press Play Dragonwilds.','success');
          } else toast('World linked','Live fingerprint verification is required before the first file sync.','success');
        } catch(error){
          if(sync&&linkedWorld&&isFileParityMismatch(error?.message||'')){closeModal();openSyncMismatchConfirmation(linkedWorld,error.message);}
          else toast(sync?'Could not link and sync':'Could not link World',error.message,'error');
        }
      };
      modalRoot.querySelector('#directory-save-link')?.addEventListener('click',()=>complete(false));
      modalRoot.querySelector('#directory-link-play')?.addEventListener('click',()=>complete(true));
    } catch(error) { toast('WebHost link rejected',error.message,'error'); }
  }

  function updateStartupProgress(done,total,label) {
    const percent=Math.max(4,Math.min(100,Math.round((done/Math.max(1,total))*100)));
    const bar=root.querySelector('.startup-progress>i');
    const status=root.querySelector('[data-startup-status]');
    if(bar)bar.style.width=`${percent}%`;
    if(status)status.textContent=label;
  }

  async function preloadCharacterStudio() {
    const [response,customItems]=await Promise.all([
      api.invoke('characters.list',{}),
      api.invoke('application.custom_items.discover',{}).catch(()=>null),
    ]);
    if(customItems?.state)state.data=customItems.state;
    state.characters=response.characters||[];state.rsdwWorlds=response.worlds||[];
    const candidate=state.characterSelectedId||response.toolkit_selected_id||state.characters.find((row)=>row.editable)?.id||'';
    state.characterSelectedId=state.characters.some((row)=>row.id===candidate)?candidate:'';
    const selected=state.characters.find((row)=>row.id===state.characterSelectedId);
    if(!selected?.editable)return;
    state.rsdwCharacterPayload=await api.invoke('characters.toolkit.read',{character_id:selected.id});
    state.rsdwCharacterCache[selected.id]={payload:state.rsdwCharacterPayload,tools:state.rsdwNativeTools};
  }

  async function prepareRsdwlServerTool(tool, world) {
    const cacheKey=`${world.id}:${tool}`;
    if(tool==='map'){
      await Promise.all([refreshServerPlayers(world,true,false),ensureAshenfallMap({world})]);
    }else if(tool==='console'){
      await refreshServerConsole(world,true,{paint:false});
    }else if(tool==='spawner'){
      await refreshServerPlayers(world,true,false);
      await refreshServerSpawner(world,{quiet:true});
    }else{
      throw new Error(`Unsupported RSDW-L server tool: ${tool}`);
    }
    state.serverTabLoadedAt[cacheKey]=Date.now();
  }

  const APPY_WARM_STORAGE_KEY='dragonwilds-sync-last-appy';
  let appliedWindowPreferenceSignature='';
  const appyWarmPromises=new Map();
  const appyWarmTimers=new Map();
  let characterStudioWarmPromise=null;

  function appyForRoute(route=state.route) {
    const value=String(route||'').toLowerCase();
    if(value==='characters-app'||value==='profile'&&state.profileTab==='characters')return 'characters';
    if(value==='mods-app'||value==='settings'&&state.settingsTab==='mods')return 'mods';
    if(value==='rsdw-launcher'||value==='rsdw-toolkit'||value==='rsdw-editor')return 'rsdw-l';
    if(['servers','server-detail','rsdragonwilds-app','world-management','world-detail'].includes(value))return 'worlds';
    if(['webhost','remote-server'].includes(value))return 'sync';
    if(value==='help')return 'shell';
    if(value==='settings')return 'system';
    return 'worlds';
  }

  function rememberLastAppy(appy) {
    const value=String(appy||'').trim();
    if(!value)return;
    try{localStorage.setItem(APPY_WARM_STORAGE_KEY,value);}catch(_){}
  }

  function lastAppy() {
    try{return String(localStorage.getItem(APPY_WARM_STORAGE_KEY)||'worlds');}catch(_){return 'worlds';}
  }

  function selectedInventoryWarmRequests() {
    const requests=[{method:'application.storage.paths',params:{}}];
    const privateId=selectedPrivateProfileId();
    if(privateWorldById(privateId))requests.push({method:'singleplayer.inventory',params:{profile_id:privateId,id:privateId,rescan:false}});
    const serverId=String(state.selectedServerWorldId||state.data?.server?.active_world_id||'');
    if(serverId&&serverWorlds().some((world)=>String(world.id)===serverId))requests.push({method:'server.world.inventory',params:{id:serverId,rescan:false}});
    return requests;
  }

  function ensureCharacterStudioWarm() {
    if(state.characters.length&&state.rsdwCharacterPayload)return Promise.resolve({cached:true});
    if(!characterStudioWarmPromise)characterStudioWarmPromise=preloadCharacterStudio().catch((error)=>{characterStudioWarmPromise=null;throw error;});
    return characterStudioWarmPromise;
  }

  function appyApplications(appy) {
    const value=String(appy||'worlds');
    if(value==='characters')return ['characters'];
    if(value==='mods')return ['mods'];
    if(value==='rsdw-l')return ['rsdw-l'];
    if(value==='rsdragonwilds')return ['worlds','rsdragonwilds'];
    if(value==='sync')return ['sync','webgui'];
    if(value==='system')return ['shell','system'];
    if(value==='shell')return ['shell'];
    return ['worlds','rsdragonwilds'];
  }

  function warmAppy(appy,{reason='idle'}={}) {
    const value=String(appy||'worlds');
    const profile=activeComputerProfile();
    if(hostingFocusActive()&&profile.reduce_background_work!==false&&['characters','mods','rsdw-l'].includes(value))return Promise.resolve({appy:value,ready:false,deferred:true});
    if(appyWarmPromises.has(value))return appyWarmPromises.get(value);
    const promise=(async()=>{
      const tasks=[api.invoke('feature.worker.prepare',{owner:`appy-${value}-${reason}`,applications:appyApplications(value),eager_only:false})];
      if(['worlds','rsdragonwilds'].includes(value))tasks.push(window.dragonwilds.prewarm?.(selectedInventoryWarmRequests()));
      if(value==='characters')tasks.push(ensureCharacterStudioWarm(),configureRsdwToolkitSource(state.data?.application?.rsdw_cache_status||null));
      if(value==='rsdw-l')tasks.push(configureRsdwToolkitSource(state.data?.application?.rsdw_cache_status||null));
      await Promise.allSettled(tasks.filter(Boolean));
      return {appy:value,ready:true};
    })();
    appyWarmPromises.set(value,promise);
    return promise;
  }

  function cancelScheduledAppyWarm(appy) {
    const value=String(appy||'');
    const pending=appyWarmTimers.get(value);
    if(!pending)return;
    clearTimeout(pending.timer);
    if(pending.idle&&typeof cancelIdleCallback==='function')cancelIdleCallback(pending.idle);
    appyWarmTimers.delete(value);
  }

  function scheduleAppyWarm(appy,{delay=100,timeout=1200}={}) {
    const value=String(appy||'').trim();
    if(!value||appyWarmPromises.has(value)||appyWarmTimers.has(value))return;
    const pending={timer:null,idle:null};
    pending.timer=setTimeout(()=>{
      const run=()=>{appyWarmTimers.delete(value);warmAppy(value,{reason:'predictive'}).catch(()=>{});};
      if(typeof requestIdleCallback==='function')pending.idle=requestIdleCallback(run,{timeout});
      else pending.timer=setTimeout(run,32);
    },Math.max(0,Number(delay)||0));
    appyWarmTimers.set(value,pending);
  }

  async function prepareLauncherWorkspaces() {
    if(detachedMode)return;
    const tasks=[
      ['Core World workspace',()=>api.invoke('feature.worker.prepare',{owner:'launcher-splash',eager_only:true,applications:['shell','worlds']})],
      ['Selected profile cache',()=>window.dragonwilds.prewarm?.(selectedInventoryWarmRequests())],
      ['Launcher integrations',()=>Promise.allSettled([
        window.dragonwilds.adminStatus?.(),window.dragonwilds.appUpdateMode?.(),window.dragonwilds.appUpdateResult?.(),
        window.dragonwilds.nexusStatus?.(),window.dragonwilds.listDetachedWindows?.(),
      ]).then((results)=>{
        if(results[0]?.status==='fulfilled'&&results[0].value)state.adminStatus=results[0].value;
        if(results[1]?.status==='fulfilled')state.applicationUpdateMode=results[1].value;
        if(results[2]?.status==='fulfilled')state.applicationUpdateResult=results[2].value;
        if(results[3]?.status==='fulfilled')state.nexusStatus=results[3].value;
        if(results[4]?.status==='fulfilled')state.detachedWindows=results[4].value||[];
      })],
    ];
    let done=0;updateStartupProgress(done,tasks.length,'Starting launcher workspaces…');
    const deadline=(task,label)=>Promise.race([
      Promise.resolve().then(task),
      new Promise((resolve)=>setTimeout(()=>resolve({deferred:true,label}),12000)),
    ]);
    await Promise.allSettled(tasks.map(async([label,task])=>{try{return await deadline(task,label);}finally{done+=1;updateStartupProgress(done,tasks.length,`Prepared ${label}`);}}));
    updateStartupProgress(tasks.length,tasks.length,'Launcher workspaces ready');
    scheduleAppyWarm(lastAppy(),{delay:80,timeout:1800});
  }

  async function bootstrap() {
    installPersistentRouteDelegation();
    if (detachedMode) {
      // A detached window is a small, purpose-built pop-out (e.g. the Runtime
      // Console), not a second launch of the application -- the full-bleed
      // animated splash used for the main window reads as "the whole program
      // is loading" in a 1240x800 utility window. Its own route already
      // paints a scoped "Opening <thing>..." placeholder (see render()'s
      // detached-window-host branches), so this only needs to bridge the gap
      // until bootstrap's state fetch resolves.
      root.className = 'detached-root';
      root.innerHTML = `<div class="detached-loading"><div class="spinner"></div><strong>Opening…</strong></div>`;
    } else {
      root.className = 'welcome-root';
      root.innerHTML = `<div class="fantasy-loading"><img class="fantasy-loading-art" src="assets/theme/animated-splash.webp" alt=""/><div class="fantasy-loading-card"><img src="assets/application-icon.webp" alt="" /><div class="spinner"></div><strong>Preparing Dragonwilds Sync</strong><span data-startup-status>Restoring Worlds, profiles, paths, and server state…</span><div class="startup-progress" role="progressbar"><i></i></div></div></div>`;
    }
    try {
      if(detachedMode && window.dragonwilds?.detachedContext){
        const detached=await window.dragonwilds.detachedContext();
        if(detached?.context && typeof detached.context==='object')detachedContext=detached.context;
      }
      state.data = await api.invoke('bootstrap');
      window.__DWSYNC_STATE__ = state.data;
      if (!state.selectedWorldId) state.selectedWorldId = state.data?.client?.active_world_id || null;
      if (!state.selectedServerWorldId) state.selectedServerWorldId = state.data?.server?.active_world_id || null;
      seedPersistedInventories(state.data);
      if (detachedMode) {
        state.entered = true;
        state.route = detachedRoute || 'profile';
        if (detachedContext.profileTab) state.profileTab = detachedContext.profileTab;
        if (detachedContext.settingsTab) state.settingsTab = detachedContext.settingsTab;
        if (detachedContext.characterId) state.characterSelectedId = detachedContext.characterId;
        if (detachedContext.characterProfileTab) state.characterProfileTab = detachedContext.characterProfileTab;
        if (detachedContext.rsdwTool) state.rsdwTool = detachedContext.rsdwTool;
        if (detachedContext.nexusTarget) state.nexusTarget = detachedContext.nexusTarget;
        if (detachedContext.selectedWorldId) state.selectedWorldId = detachedContext.selectedWorldId;
        if (detachedContext.selectedServerWorldId) state.selectedServerWorldId = detachedContext.selectedServerWorldId;
        if (detachedContext.privateTab) state.privateTab = detachedContext.privateTab;
        if (detachedContext.serverTab) state.serverTab = detachedContext.serverTab;
        if (detachedContext.modScope) state.modExplorerScope = detachedContext.modScope;
        if (detachedContext.modUnitKey) state.modExplorerUnitKey = detachedContext.modUnitKey;
        if (detachedContext.customItemSeed) state.customItemSeed = detachedContext.customItemSeed;
        if (state.route === 'rsdw-editor') {
          try {
            const response = await api.invoke('characters.list', {});
            state.characters = response.characters || [];
            state.rsdwWorlds = response.worlds || [];
            const candidate = detachedContext.characterId || response.toolkit_selected_id || state.characters[0]?.id || '';
            state.characterSelectedId = state.characters.some((character)=>character.id===candidate) ? candidate : (state.characters[0]?.id || '');
            const selected = state.characters.find((character)=>character.id===state.characterSelectedId);
            if (selected?.editable) state.rsdwCharacterPayload = await api.invoke('characters.toolkit.read', { character_id:selected.id });
          } catch (error) { state.rsdwHydrationError = error.message || String(error); }
        }
      }
      // Bootstrap already contains the durable profile/system cache. Paint the
      // usable shell immediately; warm expensive Appy caches in parallel.
      const workspaceWarmPromise=prepareLauncherWorkspaces();
      render();
      void workspaceWarmPromise.then(()=>{if(!detachedMode)render();}).catch(()=>{});
      // Native shell status, account status, update checks, and toolkit feed
      // hydration are secondary. They must never hold the first usable frame.
      if(detachedMode) Promise.allSettled([
        window.dragonwilds.adminStatus?.(),
        window.dragonwilds.appUpdateMode?.(),
        window.dragonwilds.appUpdateResult?.(),
        window.dragonwilds.nexusStatus?.(),
        Promise.resolve([]),
      ]).then((results)=>{
        if(results[0]?.status==='fulfilled'&&results[0].value)state.adminStatus=results[0].value;
        if(results[1]?.status==='fulfilled')state.applicationUpdateMode=results[1].value;
        if(results[2]?.status==='fulfilled')state.applicationUpdateResult=results[2].value;
        if(results[3]?.status==='fulfilled')state.nexusStatus=results[3].value;
        if(results[4]?.status==='fulfilled')state.detachedWindows=results[4].value||[];
        render();
      });
      if (!detachedMode && window.dragonwilds?.listDetachedWindows) {
        window.dragonwilds.onDetachedWindowsChanged?.((items)=>{ state.detachedWindows=items||[]; syncInternalTaskbar(); });
      }
      setTimeout(async()=>{
        if (!detachedMode && state.applicationUpdateResult && state.data?.application?.rsdw_cache?.refresh_after_updates !== false) {
          try { const refreshed = await api.invoke('application.rsdw.refresh', { force: false }); if (refreshed?.state) setData(refreshed.state); } catch (_) {}
        }
        const updateCfg = state.data?.application?.application_updates || {};
        if (!detachedMode && updateCfg.auto_check !== false && String(updateCfg.github_url || '').trim()) {
          try { await checkApplicationUpdate(false); } catch (_) {}
        }
      },250);
      if (detachedMode && state.route === 'mod-explorer') {
        const host=()=>document.querySelector('#mod-explorer-window');
        if(!detachedContext.modUnitKey){
          const target=host();if(target)target.innerHTML='<div class="empty-state"><strong>Mod Editor context was not received.</strong><span>Close this window and open the mod again from its profile. No file was changed.</span></div>';
        }else{
          void workspaceWarmPromise.then(()=>openModExplorer(detachedContext.modScope||'singleplayer',detachedContext.modUnitKey)).catch((error)=>{const target=host();if(target)target.innerHTML=`<div class="empty-state"><strong>Mod Editor could not hydrate.</strong><span>${escapeHtml(error?.message||String(error))}</span></div>`;});
        }
      }
      if (detachedMode && state.route === 'server-console') setTimeout(()=>openUnifiedLaunchConsole(activeServerWorld(),{inlineHost:document.querySelector('#server-console-window')}),60);
      if (detachedMode && state.route === 'custom-item-repository') setTimeout(()=>openCustomItemRepository(detachedContext.customItemSeed||{}),60);
      if (state.pendingDirectoryJoin) setTimeout(()=>openDirectoryJoin(state.pendingDirectoryJoin),80);
      // The map remains lazy: only a visible Map view warms its large asset cache.
      startBackgroundRefreshScheduler();
    } catch (error) {
      root.innerHTML = `<div class="fantasy-loading"><div class="fantasy-loading-card error-card"><strong>Could not start Dragonwilds Sync.</strong><span>${escapeHtml(error.message)}</span></div></div>`;
    }
  }

  function navButton(route, icon, label, options={}) {
    const active=Object.prototype.hasOwnProperty.call(options,'active')?!!options.active:state.route===route;
    const appy=String(options.appy||route).replace(/[^a-z0-9-]/gi,'');
    const subapps=String(options.subapps||'');
    const tone=String(options.tone||'default').replace(/[^a-z0-9-]/gi,'');
    return `<button class="nav-button appy-nav ${active?'active':''}" data-route="${route}" data-appy="${appy}" data-appy-tone="${tone}" title="${escapeHtml(subapps||label)}"><span class="nav-icon">${icon}</span><span class="appy-nav-copy"><strong>${escapeHtml(label)}</strong>${subapps?`<small>${escapeHtml(subapps)}</small>`:''}</span></button>`;
  }

  function navIconAsset(source) {
    return `<img class="nav-icon-image" src="${escapeHtml(source)}" width="22" height="22" alt="" aria-hidden="true" draggable="false" decoding="sync"/>`;
  }

  function isLinkedDirectoryEndpoint(value) {
    const raw = String(value || '').trim();
    if (!raw) return false;
    try {
      const url = new URL(/^https?:\/\//i.test(raw) ? raw : `http://${raw}`);
      const host = String(url.hostname || '').trim();
      return !!host && (host.includes('.') || host.includes(':') || /^\d{1,3}(?:\.\d{1,3}){3}$/.test(host));
    } catch (_) { return false; }
  }

  function serverManagementLoginUrl(value) {
    const raw=String(value||'').trim();
    if(!raw)return '';
    try{
      const url=new URL(/^https?:\/\//i.test(raw)?raw:`http://${raw}`);
      if(!['http:','https:'].includes(url.protocol)||!url.hostname)return '';
      if(url.protocol==='http:'&&!url.port)url.port='27080';
      url.username='';url.password='';url.hash='';url.pathname='/admin/login';
      return url.toString();
    }catch(_){return '';}
  }

  function renderTitlebar() {
    const collapsed = !!state.data?.application?.nav_collapsed;
    const notices = Array.isArray(state.data?.application?.notifications) ? state.data.application.notifications : [];
    const unread = notices.filter((item) => item && item.read !== true).length;
    const elevated = !!state.adminStatus?.elevated;
    return `<header class="titlebar">
      <div class="titlebar-left"><button class="titlebar-collapse" id="toggle-nav-collapse" title="${collapsed ? t('expandNavigation') : t('collapseNavigation')}">☰</button>${state.navigationHistory.length ? `<button class="titlebar-back" id="global-back" title="${t('back')}">←</button>` : ''}<img class="titlebar-app-icon" src="assets/application-icon.webp" alt="" /><span class="titlebar-title">Dragonwilds Sync</span></div>
      <div class="titlebar-spacer"></div>
      <span class="titlebar-privilege ${elevated?'elevated':'standard'}" title="${elevated?'Dragonwilds Sync is running with Windows Administrator rights.':'Dragonwilds Sync is running with standard Windows rights.'}">${elevated?'ADMINISTRATOR MODE':'STANDARD MODE'}</span>
      <label class="titlebar-language" title="Language / Langue / Sprache / Idioma / Lingua"><span aria-hidden="true">🌐</span><select id="application-language" aria-label="Language"><option value="en" ${languageCode()==='en'?'selected':''}>🇺🇸 English</option><option value="fr" ${languageCode()==='fr'?'selected':''}>🇫🇷 Français</option><option value="de" ${languageCode()==='de'?'selected':''}>🇩🇪 Deutsch</option><option value="es" ${languageCode()==='es'?'selected':''}>🇪🇸 Español</option><option value="it" ${languageCode()==='it'?'selected':''}>🇮🇹 Italiano</option></select></label>
      <button class="titlebar-notification" id="open-notification-center" title="${t('notifications')}">🔔${unread ? `<span>${Math.min(99, unread)}</span>` : ''}</button>
      <button class="titlebar-control" id="window-minimize" title="${t('minimize')}">—</button>
      <button class="titlebar-control" id="window-maximize" title="${t('maximize')}">□</button>
      <button class="titlebar-control titlebar-close" id="window-close" title="${t('close')}">×</button>
    </header>`;
  }

  function openNotificationCenter() {
    const items = [...(state.data?.application?.notifications || [])].filter(Boolean).sort((a,b) => Number(b.created_at || 0) - Number(a.created_at || 0));
    const bucket=(item)=>{const text=`${item.kind||''} ${item.title||''} ${item.body||''}`.toLowerCase();if(/warning|error|restart|attention/.test(text))return'warnings';if(/update|upgrade|refresh|version/.test(text))return'updates';if(item.world_id||/server|world|connection|network|host/.test(text))return'servers';return'general';};
    const notificationIdentity=(item)=>{
      const worldId=String(item.world_id||item.profile_id||'');
      const pools=[...worlds(),...privateWorlds(),...serverWorlds(),...sharedWorldProfiles(),...(state.data?.client?.discovered_worlds||[]),...(state.data?.client?.directory_worlds||[])];
      const world=pools.find((entry)=>String(entry?.id||entry?.profile_id||'')===worldId);
      const presentation=world?.presentation||world?.profile?.presentation||{};
      const profileMatch=worldId&&String(state.data?.player_profile?.id||'')===worldId?state.data.player_profile:null;
      return {
        label:String(world?.name||world?.nickname||world?.identity?.world_name||world?.profile_name||profileMatch?.display_name||''),
        icon:b64Image(presentation.icon_b64||world?.icon_b64||world?.profile?.icon_b64)||profileMatch?.avatar_data||'assets/application-icon.webp',
        banner:b64Image(presentation.banner_b64||world?.banner_b64||world?.profile?.banner_b64)||profileMatch?.banner_data||'',
      };
    };
    const openSyncReceipt=(item)=>{
      const receipt=item?.details||{},files=Array.isArray(receipt.files)?receipt.files:[];
      const runtimeIcon=(file)=>{const value=`${file.runtime_type||''} ${file.category||''} ${file.path||''}`.toLowerCase();if(value.includes('dragonlink')||value.includes('connect'))return'assets/application-icon.webp';if(value.includes('runeschema'))return'assets/platforms/runeschema.webp';if(value.includes('ue4ss'))return'assets/platforms/ue4ss.webp';if(value.includes('pak'))return'assets/platforms/paks.svg';return'assets/rsdw-toolkit/modded-items.svg';};
      const verified=receipt.acknowledgements?.host_match_confirmed===true;
      showModal(`<div class="modal-header"><div><div class="eyebrow">Verified Transfer Transaction</div><h2>${escapeHtml(notificationIdentity(item).label||'World Sync')} Receipt</h2><p>${verified?'The client and host acknowledged the same manifest.':'The host acknowledgement was not recorded.'}</p></div><button class="modal-close" data-close-modal>×</button></div><div class="modal-body"><div class="metric-grid">${metric('Downloaded',String(receipt.downloaded||0))}${metric('Transferred',formatBytes(receipt.downloaded_bytes||0))}${metric('Removed',String(receipt.removed||0))}${metric('Already current',String(receipt.unchanged||0))}</div><div class="identity-box"><strong>Manifest fingerprint</strong><p>${escapeHtml(receipt.manifest_fingerprint||'Unavailable')}</p></div><div class="transfer-receipt-list">${files.length?files.map(file=>{const loader=String(file.runtime_type||file.category||'FILE').replaceAll('_',' ');return`<article class="transfer-receipt-row"><img src="${runtimeIcon(file)}" alt="${escapeHtml(loader)} loader" title="${escapeHtml(loader)}"><div><strong>${escapeHtml(String(file.path||'Downloaded file').split('/').pop())}</strong><small>${escapeHtml(file.path||'')} · ${formatBytes(file.size||0)}</small></div><span>${escapeHtml(loader)}</span></article>`;}).join(''):'<div class="empty-state compact">No payload bytes were required; every advertised file was already current.</div>'}</div></div><div class="modal-footer"><span>Passwords and bearer credentials are never included.</span><button class="btn primary" data-close-modal>Done</button></div>`,{title:'World Sync Receipt',width:900,height:720});
    };
    const rows=items.map((item) => { const steamCloud=item.title==='Steam Cloud is enabled for Dragonwilds',receipt=item.details?.type==='sync_receipt',identity=notificationIdentity(item);return `<div class="notification-center-row ${item.read ? '' : 'unread'} ${identity.banner?'has-identity-banner':''} ${steamCloud?'steam-cloud-action':''} ${receipt?'sync-receipt-action':''}" data-notification-row data-notification-id="${escapeHtml(item.id||'')}" data-notification-bucket="${bucket(item)}" data-notification-unread="${item.read===true?'0':'1'}" ${(steamCloud||receipt)?'role="button" tabindex="0"':''}>${identity.banner?`<img class="notification-row-banner" src="${escapeHtml(identity.banner)}" alt=""/>`:''}<div class="notification-kind ${escapeHtml(item.kind || 'info')}"></div><img class="notification-profile-icon" src="${escapeHtml(identity.icon)}" alt=""/><div class="notification-row-copy"><strong>${escapeHtml(item.title || 'Dragonwilds Sync')}</strong>${identity.label?`<span>${escapeHtml(identity.label)}</span>`:''}<p>${escapeHtml(item.body || '')}</p><small>${item.created_at ? new Date(Number(item.created_at) * 1000).toLocaleString() : ''}</small></div><div class="notification-row-actions">${steamCloud?'<button class="btn primary compact-btn" data-open-steam-cloud-settings>Open Steam</button>':''}${receipt?`<button class="btn primary compact-btn" data-open-sync-receipt="${escapeHtml(item.id||'')}">View Receipt</button>`:''}<button class="btn ghost compact-btn" data-dismiss-notification="${escapeHtml(item.id || '')}">Dismiss</button></div></div>`;}).join('');
    showModal(`<div class="modal-header"><div><div class="eyebrow">Launcher</div><h2>Notifications</h2><p>Server operations, restart windows, updates, and connection notices.</p></div><button class="modal-close" data-close-modal>×</button></div><div class="modal-body notification-center-body"><div class="notification-filter-bar"><button class="btn primary compact-btn" data-notification-filter="all">All</button><button class="btn ghost compact-btn" data-notification-filter="unread">Unread</button><button class="btn ghost compact-btn" data-notification-filter="warnings">Warnings</button><button class="btn ghost compact-btn" data-notification-filter="updates">Updates</button><button class="btn ghost compact-btn" data-notification-filter="servers">Worlds &amp; Servers</button></div>${items.length ? `<div class="notification-center-list">${rows}</div>` : '<div class="empty-state">No notifications yet.</div>'}</div><div class="modal-footer"><button class="btn ghost" id="clear-notifications" ${items.length ? '' : 'disabled'}>Dismiss All</button><div class="footer-right"><button class="btn primary" data-close-modal>Done</button></div></div>`,{title:'Notifications',width:980,height:760});
    let activeFilter='all';
    const localNotifications=()=>state.data?.application?.notifications||[];
    const syncNotificationCenterEmptyState=()=>{const list=modalRoot.querySelector('.notification-center-list');if(list&&!list.querySelector('[data-notification-row]'))list.replaceWith(Object.assign(document.createElement('div'),{className:'empty-state',textContent:'No notifications yet.'}));const clear=modalRoot.querySelector('#clear-notifications');if(clear)clear.disabled=!localNotifications().length;root.querySelector('#open-notification-center span')?.remove();};
    const applyFilter=()=>{modalRoot.querySelectorAll('[data-notification-row]').forEach((row)=>{row.hidden=activeFilter!=='all'&&(activeFilter==='unread'?row.dataset.notificationUnread!=='1':row.dataset.notificationBucket!==activeFilter);});modalRoot.querySelectorAll('[data-notification-filter]').forEach((button)=>{const active=button.dataset.notificationFilter===activeFilter;button.classList.toggle('primary',active);button.classList.toggle('ghost',!active);});};
    modalRoot.querySelectorAll('[data-notification-filter]').forEach((button)=>button.addEventListener('click',()=>{activeFilter=button.dataset.notificationFilter||'all';applyFilter();}));
    modalRoot.querySelectorAll('[data-open-sync-receipt]').forEach((button)=>button.addEventListener('click',(event)=>{event.stopPropagation();const item=items.find(row=>String(row.id||'')===String(button.dataset.openSyncReceipt||''));if(item)openSyncReceipt(item);}));
    modalRoot.querySelectorAll('.sync-receipt-action').forEach((row)=>{const open=()=>{const item=items.find(entry=>String(entry.id||'')===String(row.dataset.notificationId||''));if(item)openSyncReceipt(item);};row.addEventListener('click',(event)=>{if(!event.target.closest('button'))open();});row.addEventListener('keydown',(event)=>{if((event.key==='Enter'||event.key===' ')&&!event.target.closest('button')){event.preventDefault();open();}});});
    if (items.some((item) => item.read !== true)) { items.forEach((item)=>item.read=true);localNotifications().forEach((item)=>{if(item)item.read=true;});root.querySelector('#open-notification-center span')?.remove();api.invoke('notifications.mark_all_read', {}).catch(()=>{}); }
    modalRoot.querySelectorAll('[data-dismiss-notification]').forEach((button) => button.addEventListener('click', (event) => { event.stopPropagation();const id=button.dataset.dismissNotification;const row=button.closest('.notification-center-row');state.data.application.notifications=localNotifications().filter((item)=>String(item?.id||'')!==String(id||''));row?.remove();syncNotificationCenterEmptyState();applyFilter();api.invoke('notifications.dismiss',{id}).catch((error)=>toast('Notification dismissal was not saved',error.message,'error')); }));
    modalRoot.querySelectorAll('[data-open-steam-cloud-settings]').forEach((element) => { element.addEventListener('click',(event)=>{event.stopPropagation();openSteamCloudSettings();});element.addEventListener('keydown',(event)=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();openSteamCloudSettings();}}); });
    modalRoot.querySelector('#clear-notifications')?.addEventListener('click', () => { state.data.application.notifications=[];const list=modalRoot.querySelector('.notification-center-list');if(list)list.replaceWith(Object.assign(document.createElement('div'),{className:'empty-state',textContent:'No notifications yet.'}));syncNotificationCenterEmptyState();api.invoke('notifications.clear',{}).catch((error)=>toast('Notification dismissal was not saved',error.message,'error')); });
  }

  function renderSidebar() {
    const p = player();
    const avatar = p.avatar_data ? `<img src="${p.avatar_data}" alt="" />` : escapeHtml(initials(p.display_name || 'Player'));
    const dragonwildsActive=['world-management','world-detail','server-detail','servers','rsdragonwilds-app','worlds'].includes(state.route);
    const charactersActive=state.route==='profile'&&state.profileTab==='characters';
    const modsActive=state.route==='mods-app'||(state.route==='settings'&&state.settingsTab==='mods');
    const rsdwLauncherActive=state.route==='rsdw-launcher';
    const systemSettingsActive=state.route==='settings'&&!modsActive;
    return `
      <aside class="sidebar">
        <div class="brand">
          <img src="assets/application-icon.webp" alt="" />
          <div class="brand-copy"><strong>Dragonwilds Sync</strong><span>${t('worldLauncher')}</span></div>
        </div>
        <div class="nav-label">Play &amp; Create</div>
        ${navButton('world-management',navIconAsset('assets/navigation/dragonwilds.webp'),'Dragonwilds',{appy:'worlds',tone:'worlds',active:dragonwildsActive,subapps:'Singleplayer · Co-Op · Dedicated · connect'})}
        ${navButton('characters-app',navIconAsset('assets/rsdw-toolkit/character-editor.webp'),'Characters',{appy:'characters',tone:'characters',active:charactersActive,subapps:'Saves · identity · appearance'})}
        ${navButton('mods-app',navIconAsset('assets/navigation/mods.webp'),'Mods',{appy:'mods',tone:'mods',active:modsActive,subapps:'Repository · editor · load order'})}
        ${navButton('rsdw-launcher',navIconAsset('assets/navigation/rsdw-l.webp'),'RSDW-L',{appy:'rsdw-l',tone:'characters',active:rsdwLauncherActive,subapps:'Editors · map · spawner · console'})}
        <div class="nav-label">Host &amp; Connect</div>
        ${navButton('webhost',navIconAsset('assets/navigation/sync.svg'),'Sync',{appy:'sync',tone:'sync',subapps:'Directory · transfer · remote'})}
        <div class="nav-label">${t('system')}</div>
        ${navButton('help',navIconAsset('assets/navigation/help.svg'),'Helpy',{appy:'help',tone:'system',subapps:'Guides · screenshots · safety'})}
        ${navButton('trash','<span aria-hidden="true">♲</span>','Trash',{appy:'system',tone:'system',subapps:'Restore · permanently delete · retention'})}
        ${navButton('settings',navIconAsset('assets/navigation/settings.svg'),t('settings'),{appy:'system',tone:'system',active:systemSettingsActive,subapps:'Application · network · updates'})}
        <div class="sidebar-spacer"></div>
        <button class="player-chip ${state.route==='profile'?'active':''}" id="player-chip">
          <div class="avatar">${avatar}</div>
          <div><strong>${escapeHtml(p.display_name || 'Player')}</strong><span>Profile Management</span></div>
          <div class="chev">›</div>
        </button>
      </aside>`;
  }

  const persistentShellBindings=new WeakMap();
  function bindPersistentOnce(node,eventName,key,handler) {
    if(!node)return;
    let keys=persistentShellBindings.get(node);
    if(!keys){keys=new Set();persistentShellBindings.set(node,keys);}
    const token=`${eventName}:${key}`;
    if(keys.has(token))return;
    keys.add(token);node.addEventListener(eventName,handler);
  }

  function syncTransientShellMarkup(host,markup) {
    if(!host)return false;
    const next=String(markup||'');
    if(host.__dwsShellMarkup===next)return false;
    host.__dwsShellMarkup=next;
    host.innerHTML=next;
    return true;
  }

  function syncShellText(node,value) {
    const next=String(value??'');
    if(node&&node.textContent!==next)node.textContent=next;
  }

  function syncShellTitle(node,value) {
    const next=String(value??'');
    if(node&&node.title!==next)node.title=next;
  }

  function syncPersistentTitlebar(titlebar) {
    if(!titlebar)return;
    const collapsed=!!state.data?.application?.nav_collapsed;
    const collapse=titlebar.querySelector('#toggle-nav-collapse');
    syncShellTitle(collapse,collapsed?t('expandNavigation'):t('collapseNavigation'));
    const left=titlebar.querySelector('.titlebar-left');
    let back=titlebar.querySelector('#global-back');
    if(state.navigationHistory.length&&!back&&left){
      back=document.createElement('button');back.className='titlebar-back';back.id='global-back';back.textContent='←';
      left.insertBefore(back,left.querySelector('.titlebar-app-icon'));
    }else if(!state.navigationHistory.length&&back){back.remove();back=null;}
    syncShellTitle(back,t('back'));

    const elevated=!!state.adminStatus?.elevated;
    const privilege=titlebar.querySelector('.titlebar-privilege');
    if(privilege){
      privilege.classList.toggle('elevated',elevated);privilege.classList.toggle('standard',!elevated);
      syncShellText(privilege,elevated?'ADMINISTRATOR MODE':'STANDARD MODE');
      syncShellTitle(privilege,elevated?'Dragonwilds Sync is running with Windows Administrator rights.':'Dragonwilds Sync is running with standard Windows rights.');
    }
    const language=titlebar.querySelector('#application-language');
    if(language&&language.value!==languageCode())language.value=languageCode();
    const notices=Array.isArray(state.data?.application?.notifications)?state.data.application.notifications:[];
    const unread=notices.filter((item)=>item&&item.read!==true).length;
    const notifications=titlebar.querySelector('#open-notification-center');
    if(notifications){
      syncShellTitle(notifications,t('notifications'));
      let badge=notifications.querySelector('span');
      if(unread){if(!badge){badge=document.createElement('span');notifications.appendChild(badge);}syncShellText(badge,String(Math.min(99,unread)));}
      else badge?.remove();
    }
    syncShellTitle(titlebar.querySelector('#window-minimize'),t('minimize'));
    syncShellTitle(titlebar.querySelector('#window-maximize'),t('maximize'));
    syncShellTitle(titlebar.querySelector('#window-close'),t('close'));
  }

  function syncPersistentSidebar(sidebar) {
    if(!sidebar)return;
    const p=player();
    const activeRoutes={
      'world-management':['world-management','world-detail','server-detail','servers','rsdragonwilds-app','worlds'].includes(state.route),
      'characters-app':state.route==='profile'&&state.profileTab==='characters',
      'mods-app':state.route==='mods-app'||(state.route==='settings'&&state.settingsTab==='mods'),
      'rsdw-launcher':state.route==='rsdw-launcher',
      webhost:state.route==='webhost'||state.route==='remote-server',
      help:state.route==='help',
      settings:state.route==='settings'&&state.settingsTab!=='mods',
    };
    sidebar.querySelectorAll('.appy-nav[data-route]').forEach((button)=>{
      const active=!!activeRoutes[button.dataset.route];
      button.classList.toggle('active',active);
      if(active&&button.getAttribute('aria-current')!=='page')button.setAttribute('aria-current','page');
      else if(!active&&button.hasAttribute('aria-current'))button.removeAttribute('aria-current');
    });
    const hostConfig=state.data?.application?.world_directory_host||{};
    const hostStatus=state.data?.application?.world_directory_host_status||{};
    const syncButton=sidebar.querySelector('.appy-nav[data-route="webhost"]');
    if(syncButton){const linked=isLinkedDirectoryEndpoint(hostStatus.public_url||hostConfig.public_base_url)?'1':'0';if(syncButton.dataset.linked!==linked)syncButton.dataset.linked=linked;}
    syncShellText(sidebar.querySelector('.brand-copy span'),t('worldLauncher'));
    const groupLabels=sidebar.querySelectorAll('.nav-label');syncShellText(groupLabels[2],t('system'));
    syncShellText(sidebar.querySelector('.appy-nav[data-route="settings"] .appy-nav-copy strong'),t('settings'));

    const chip=sidebar.querySelector('#player-chip');
    if(chip){
      chip.classList.toggle('active',state.route==='profile');
      const avatar=chip.querySelector('.avatar');
      const avatarData=String(p.avatar_data||'');
      const avatarKey=avatarData?`image:${avatarData.length}:${avatarData.slice(-24)}`:`initials:${initials(p.display_name||'Player')}`;
      if(avatar&&avatar.__dwsAvatarKey!==avatarKey){
        avatar.__dwsAvatarKey=avatarKey;avatar.replaceChildren();
        if(avatarData){const image=document.createElement('img');image.src=avatarData;image.alt='';avatar.appendChild(image);}
        else avatar.textContent=initials(p.display_name||'Player');
      }
      syncShellText(chip.querySelector('div:nth-child(2) strong'),p.display_name||'Player');
      syncShellText(chip.querySelector('div:nth-child(2) span'),'Profile Management');
    }
  }

  function renderPersistentShell(page) {
    const mounted=root.dataset.persistentShell==='1'&&root.querySelector(':scope > .titlebar')&&root.querySelector(':scope > .sidebar')&&root.querySelector(':scope > .main');
    if(!mounted){
      root.innerHTML=`${renderTitlebar()}${renderSidebar()}<div class="shell-transient-host" data-shell-operation></div><div class="shell-transient-host" data-shell-hosting-focus></div><main class="main"></main>`;
      root.dataset.persistentShell='1';
    }
    syncPersistentTitlebar(root.querySelector(':scope > .titlebar'));
    syncPersistentSidebar(root.querySelector(':scope > .sidebar'));
    const operationChanged=syncTransientShellMarkup(root.querySelector('[data-shell-operation]'),operationMarkup());
    const hostingChanged=syncTransientShellMarkup(root.querySelector('[data-shell-hosting-focus]'),hostingFocusMarkup());
    if(hostingChanged)bindPersistentOnce(root.querySelector('#dismiss-hosting-focus'),'click','dismiss-hosting-focus',()=>{state.hostingFocusDismissedProfileId=String(state.data?.server?.runtime?.active_profile_id||state.data?.server?.active_world_id||'');render();});
    const main=root.querySelector(':scope > .main');
    const pageChanged=!mounted||main.__dwsPageMarkup!==page;
    if(pageChanged){
      const retainedConsole=main.querySelector('[data-world-runtime-console][data-unified-launch-console]');
      const retainedWorldId=retainedConsole?.dataset.worldId||'';
      const keepConsole=!!(retainedConsole&&retainedWorldId&&page.includes(`data-world-runtime-console data-world-id="${retainedWorldId}"`));
      main.__dwsPageMarkup=page;
      main.innerHTML=page;
      if(keepConsole){
        const replacement=main.querySelector(`[data-world-runtime-console][data-world-id="${CSS.escape(retainedWorldId)}"]`);
        replacement?.replaceWith(retainedConsole);
      }
    }
    return {main,changed:pageChanged,transientChanged:operationChanged||hostingChanged};
  }

  // The public directory surface is intentionally a small independent module.
  // Give it one narrow handoff into the application's verified join flow so it
  // never handles or persists World passwords itself.
  window.__DWSYNC_OPEN_DIRECTORY_JOIN__ = openDirectoryJoin;

  function renderSettingsPanelSwap(updateState) {
    const main=root.querySelector(':scope > .main');
    const content=main?.querySelector(':scope > .content');
    if(state.route!=='settings'||!main||!content){updateState();render();return;}
    const stableHeader=content.querySelector(':scope > .page-header');
    const stableNav=content.querySelector('.settings-layout > .settings-nav');
    const stableSubnav=content.querySelector('.settings-layout > div > .settings-subnav');
    const scrollTop=main.scrollTop;
    updateState();
    state.scrollPositions.settings=scrollTop;
    render();
    const nextContent=main.querySelector(':scope > .content');
    const syncButtons=(stable,fresh,dataKey)=>{
      if(!stable||!fresh)return;
      stable.querySelectorAll(`button[data-${dataKey}]`).forEach((button)=>{
        const value=button.getAttribute(`data-${dataKey}`);
        const counterpart=[...fresh.querySelectorAll(`button[data-${dataKey}]`)].find((row)=>row.getAttribute(`data-${dataKey}`)===value);
        if(counterpart)button.className=counterpart.className;
      });
      fresh.replaceWith(stable);
    };
    const nextHeader=nextContent?.querySelector(':scope > .page-header');
    if(stableHeader&&nextHeader)nextHeader.replaceWith(stableHeader);
    syncButtons(stableNav,nextContent?.querySelector('.settings-layout > .settings-nav'),'settings-tab');
    syncButtons(stableSubnav,nextContent?.querySelector('.settings-layout > div > .settings-subnav'),'application-settings-tab');
    main.scrollTop=scrollTop;
    requestAnimationFrame(()=>{main.scrollTop=scrollTop;});
  }

  async function configureRsdwToolkitSource(status = null) {
    let info = status;
    try { if (!info) info = await api.invoke('application.rsdw.status', {}); } catch (_) { info = {}; }
    if (info?.toolkit_valid && info?.website_dir) {
      try {
        const configured = await window.dragonwilds.configureRsdwToolkitRoot(info.website_dir);
        if (configured?.ok) {
          const health=await fetch(new URL('__health',configured.baseUrl),{cache:'no-store'});
          if(!health.ok)throw new Error(`Local RSDW service health check failed (${health.status})`);
          state.rsdwSource = { mode:'local', baseUrl:configured.baseUrl || 'https://rsdwtools.com/', revision:String(info.revision || ''), toolkitValid:true, modelValid:!!info.model_valid, modelRevision:String(info.model_revision||'') };
          return state.rsdwSource;
        }
      } catch (_) {}
    }
    state.rsdwSource = { mode:'remote', baseUrl:'https://rsdwtools.com/', revision:String(info?.revision || ''), toolkitValid:false, modelValid:false, modelRevision:String(info?.model_revision||'') };
    return state.rsdwSource;
  }

  async function ensureRsdwToolkitSource({ force = false, quiet = true } = {}) {
    if (state.rsdwSourceBusy) return state.rsdwSource;
    state.rsdwSourceBusy = true;
    try {
      let status = await api.invoke('application.rsdw.status', {});
      if (force || !status?.toolkit_valid || !status?.model_valid) {
        try {
          const refreshed = await api.invoke('application.rsdw.refresh', { force });
          if (refreshed?.state) state.data = refreshed.state;
          status = refreshed?.result || refreshed || await api.invoke('application.rsdw.status', {});
          if (!quiet) toast('RSDW Toolkit refreshed', `${status?.data_file_count || 0} data files · local editor site cached`, 'success');
        } catch (error) {
          if (!quiet) toast('Local RSDW Toolkit refresh failed', `${error.message} · Official web fallback remains available.`, 'error');
        }
      }
      return await configureRsdwToolkitSource(status);
    } finally { state.rsdwSourceBusy = false; }
  }

  async function selectRsdwCharacter(characterId, { renderFirst = true } = {}) {
    const id = String(characterId || '');
    const selected = state.characters.find((character)=>character.id===id);
    if (!selected) return;
    state.characterSelectedId = id;
    state.rsdwHydrationError = '';
    const cached=state.rsdwCharacterCache[id];
    state.rsdwCharacterPayload = cached?.payload||null;
    state.rsdwNativeDraft = null;
    state.rsdwCharacterHistory = [];
    state.rsdwPreviewPending = false;
    state.rsdwPreviewAvatar = state.rsdwCharacterPayload?.avatar || null;
    state.rsdwPendingAvatar = null;
    state.rsdwPendingWeaponItems = {};
    state.rsdwCharacterFuture = [];
    state.rsdwCharacterLastChanges = null;
    state.rsdwNativeTools = cached?.tools||{};
    state.rsdwNativeToolBusy = '';
    state.rsdwSpellWheel = [];
    state.rsdwEquipmentRepositorySlot = '';
    const token = ++state.rsdwHydrationToken;
    if (renderFirst) render();
    try {
      const selectedState = await api.invoke('characters.toolkit.select', { character_id:id });
      if (selectedState?.state) state.data = selectedState.state;
      if (!selected.editable) {
        if (token !== state.rsdwHydrationToken) return;
        state.rsdwHydrationError = selected.viewer_note || 'This save is preserve-only. RSDWTools editors require a safely parseable JSON character document.';
        render();
        return;
      }
      const payload = await api.invoke('characters.toolkit.read', { character_id:id });
      if (token !== state.rsdwHydrationToken) return;
      state.rsdwCharacterPayload = payload;
      state.rsdwHydrationError = '';
      state.rsdwCharacterCache[id]={payload,tools:state.rsdwNativeTools};
      // The 3D preview reads state.rsdwPreviewAvatar (falling back to the
      // payload only when that is unset -- see rsdwAvatarUrl()'s caller in
      // the character-editor renderer), so once this character's *fresh*
      // save data has actually loaded, the preview must be pointed at it
      // too. Leaving rsdwPreviewAvatar on whatever was set from a stale
      // cached snapshot (or an earlier character) is exactly what makes the
      // avatar look like it's ignoring armor/hair/skin color changes: it is
      // still rendering old appearance data that this fetch just replaced.
      // A change already staged via "See changes" (rsdwPendingAvatar) takes
      // priority, since it reflects an edit the operator hasn't saved yet.
      if (!state.rsdwPendingAvatar) state.rsdwPreviewAvatar = payload?.avatar || null;
      render();
      // Parse only the visible subsystem. Other tabs hydrate on first use.
      if(state.rsdwTool!=='character-editor')setTimeout(()=>hydrateNativeRsdwTool(state.rsdwTool),0);
      else setTimeout(()=>hydrateNativeRsdwTool('item-editor',{paintStart:false}),0);
    } catch (error) {
      if (token !== state.rsdwHydrationToken) return;
      state.rsdwHydrationError = error.message || String(error);
      render();
    }
  }

  async function hydrateNativeRsdwTool(toolId,{paintStart=true}={}) {
    const tool=String(toolId||'');
    if(!tool||tool==='character-editor'||state.rsdwNativeTools[tool]||state.rsdwNativeToolBusy===tool)return;
    const selected=state.characters.find((character)=>character.id===state.characterSelectedId);
    const loaded=state.rsdwCharacterPayload;
    if(!selected?.editable||!loaded?.text)return;
    state.rsdwNativeToolBusy=tool;
    state.rsdwNativeToolProgress=18;
    try{
      const baseText=state.rsdwNativeDraft?.characterId===selected.id&&state.rsdwNativeDraft?.text?state.rsdwNativeDraft.text:loaded.text;
      state.rsdwNativeToolProgress=48;if(paintStart)render();
      const response=await api.invoke('characters.native.tool.read',{text:baseText,tool});
      state.rsdwNativeTools[tool]=response.native_tool;
      state.rsdwNativeToolProgress=100;
    }catch(error){
      state.rsdwHydrationError=error.message||String(error);
      toast('Character editor could not load',state.rsdwHydrationError,'error');
    }finally{
      if(state.rsdwNativeToolBusy===tool)state.rsdwNativeToolBusy='';
      render();
    }
  }

  async function previewRsdwToolChange(tool, change, { paint = true } = {}) {
    const selected=state.characters.find((character)=>character.id===state.characterSelectedId);
    const loaded=state.rsdwCharacterPayload;
    if(!selected?.editable||!loaded?.text)throw new Error('Select an editable character first.');
    const baseText=state.rsdwNativeDraft?.characterId===selected.id&&state.rsdwNativeDraft?.text?state.rsdwNativeDraft.text:loaded.text;
    const response=await api.invoke('characters.native.tool.preview',{text:baseText,tool,change});
    if(tool==='item-editor')rememberRsdwCharacterSnapshot();
    state.rsdwNativeDraft={...response,characterId:selected.id};
    if(response.native_tool)state.rsdwNativeTools[tool]=response.native_tool;
    if(tool==='item-editor'){
      root?.querySelectorAll?.('#rsdw-save-character, [data-character-save]').forEach((button)=>{button.disabled=false;});
      const dirty=root?.querySelector?.('[data-character-dirty]');if(dirty){dirty.classList.add('dirty');dirty.textContent='Unsaved changes';}
      const status=root?.querySelector?.('#rsdw-editor-status');if(status)status.textContent='Unsaved equipment · ready to write with backup';
      const dot=root?.querySelector?.('#rsdw-editor-status-dot');if(dot)dot.className='dirty';
    }
    if(paint)render();
    return response;
  }

  async function applyRsdwDraft() {
    const selected=state.characters.find((character)=>character.id===state.characterSelectedId);
    const loaded=state.rsdwCharacterPayload;
    const draft=state.rsdwNativeDraft;
    if(!selected||!loaded||!draft?.text||draft.characterId!==selected.id)return false;
    const response=await api.invoke('characters.toolkit.write',{character_id:selected.id,text:draft.text,expected_sha256:loaded.sha256||''});
    if(response.state)state.data=response.state;
    state.characters=response.characters?.characters||state.characters;
    toast('Character updated',`Backup: ${response.result?.backup||'created'} · written, reparsed, and verified`,'success');
    await selectRsdwCharacter(selected.id,{renderFirst:false});
    return true;
  }

  async function discardRsdwDraft() {
    const selected=state.characters.find((character)=>character.id===state.characterSelectedId);
    if(!selected)return;
    state.rsdwNativeDraft=null;
    state.rsdwCharacterHistory=[];
    state.rsdwCharacterFuture=[];
    state.rsdwCharacterLastChanges=null;
    state.rsdwNativeTools={};
    state.rsdwEquipmentRepositorySlot='';
    await selectRsdwCharacter(selected.id,{renderFirst:false});
  }

  function cloneRsdwSnapshot(value) {
    if(value==null)return null;
    try{return structuredClone(value);}catch(_){return JSON.parse(JSON.stringify(value));}
  }

  function rememberRsdwCharacterSnapshot() {
    const snapshot={draft:cloneRsdwSnapshot(state.rsdwNativeDraft),itemEditor:cloneRsdwSnapshot(state.rsdwNativeTools['item-editor']||null)};
    const prior=state.rsdwCharacterHistory[state.rsdwCharacterHistory.length-1];
    const signature=(value)=>`${value?.draft?.text||value?.draft?.sha256||'base'}|${JSON.stringify(value?.itemEditor?.sections?.loadout||[])}`;
    if(!state.rsdwCharacterHistory.length||signature(prior)!==signature(snapshot))state.rsdwCharacterHistory.push(snapshot);
    if(state.rsdwCharacterHistory.length>40)state.rsdwCharacterHistory.shift();
    state.rsdwCharacterFuture=[];
    root?.querySelectorAll?.('[data-character-undo]').forEach((button)=>{button.disabled=!state.rsdwCharacterHistory.length;});
    root?.querySelectorAll?.('[data-character-redo]').forEach((button)=>{button.disabled=true;});
  }

  async function enterRsdwToolkit({ forceSource = false, remember = true } = {}) {
    if (remember && !(state.route === 'profile' && state.profileTab === 'characters')) pushNavigation();
    state.route = 'profile';
    state.profileTab = 'characters';
    // Character Creator is a fresh navigation target, not a continuation of
    // the last editor's scroll position.
    state.scrollPositions.profile = 0;
    state.rsdwToolkitLoading = true;
    render();
    try {
      const response = await api.invoke('characters.list', {});
      state.characters = response.characters || [];
      state.rsdwWorlds = response.worlds || [];
      const candidate = state.characterSelectedId || response.toolkit_selected_id || state.characters[0]?.id || '';
      state.characterSelectedId = state.characters.some((character)=>character.id===candidate) ? candidate : (state.characters[0]?.id || '');
      state.rsdwToolkitLoading = false;
      // Resolve the local avatar/model indexes before parsing the selected save.
      // Without this ordering the first character read can resolve no hair or
      // armor, leaving the otherwise-valid 3D preview stuck on its base model.
      try { await ensureRsdwToolkitSource({ force: forceSource, quiet: !forceSource }); }
      catch (error) { state.rsdwHydrationError=error.message||String(error); }
      if (state.characterSelectedId) return selectRsdwCharacter(state.characterSelectedId, { renderFirst:false });
      render();
    } catch (error) {
      state.rsdwToolkitLoading = false;
      state.rsdwHydrationError = error.message || String(error);
      render();
    }
  }

  function rsdwWorldName(id) {
    return state.rsdwWorlds.find((world)=>String(world.id)===String(id))?.name || String(id || 'World');
  }

  function rsdwMapWorld() {
    const available = [singleplayerWorld(), ...serverWorlds()].filter(Boolean);
    return available.find((world)=>String(world.id)===String(state.rsdwMapWorldId || '')) || available.find((world)=>String(world.id)===String(state.data?.server?.active_world_id || '')) || available[0] || null;
  }

  function profileTabs() {
    return `<div class="rsdw-section-tabs profile-tabs"><button class="${state.profileTab==='user'?'active':''}" data-profile-tab="user">${t('userProfile')}</button><button class="${state.profileTab==='characters'?'active':''}" data-profile-tab="characters">${t('characters')}</button></div>`;
  }
  function rsdwToolkitTabs() { return profileTabs(); }

  function characterProfileTabs(selected) {
    if (!selected) return '';
    if(state.characterProfileTab!=='overview')state.characterProfileTab='overview';
    return '';
  }

  function renderUserProfile() {
    const p = player();
    const avatar = p.avatar_data ? `<img src="${p.avatar_data}" alt="" />` : escapeHtml(initials(p.display_name || 'Player'));
    const banner = p.banner_data ? `<img class="profile-page-banner-img" src="${p.banner_data}" alt="" />` : '';
    const socials = p.social_links || {};
    const socialDefinitions = [
      ['steam','Steam','ST'],['nexus','Nexus Mods','N'],['epic','Epic Games','E'],['xbox','Xbox','X'],
      ['playstation','PlayStation','PS'],['nintendo','Nintendo','N'],['discord','Discord','D'],
      ['github','GitHub','GH'],['twitch','Twitch','T'],['youtube','YouTube','YT'],['website','Website','↗'],
    ];
    const socialRows = socialDefinitions.filter(([key])=>String(socials[key]||'').trim()).map(([key,label,mark])=>{
      const value=String(socials[key]||'').trim();
      const action=/^https?:\/\//i.test(value)?`<button class="profile-social-link" data-open-external="${escapeHtml(value)}" title="Open ${escapeHtml(label)}"><span>${escapeHtml(value)}</span><b>↗</b></button>`:`<strong>${escapeHtml(value)}</strong>`;
      return `<div class="profile-social-row ${escapeHtml(key)}"><span class="profile-social-brand">${platformLogo(key,label)}${escapeHtml(label)}</span>${action}</div>`;
    }).join('') || '<span class="muted-small">No socials added yet. Use Edit Profile to add your gaming and community accounts.</span>';
    const profileCharacterCount=Object.keys(p.character_profiles||{}).length;
    const characterCount=Math.max((state.characters||[]).length,profileCharacterCount);
    const nexusState=state.nexusStatus?.connected?`Nexus connected · ${state.nexusStatus.username||'Account'}`:'Nexus account not connected';
    const characterRows=(state.characters||[]).map((character)=>{
      const meta=character.profile||{};
      const name=meta.label||character.player_name||character.file_name||'Character';
      const worldIds=[...new Set([...(character.world_ids||[]),...(character.selected_for_worlds||[])].map(String))];
      const worlds=worldIds.map((id)=>`<span class="world-link-chip">${escapeHtml(rsdwWorldName(id))}${(character.selected_for_worlds||[]).map(String).includes(id)?' · Preferred':''}</span>`).join('')||'<span class="muted-small">Not associated with a World profile yet.</span>';
      const portrait=meta.portrait_data?`<img src="${escapeHtml(meta.portrait_data)}" alt=""/>`:`<span>${escapeHtml(initials(name))}</span>`;
      const modified=Number(character.modified_at||0)>0?new Date(Number(character.modified_at)*1000).toLocaleString():'Timestamp unavailable';
      return `<article class="profile-character-save" data-profile-character-save="${escapeHtml(character.id)}"><div class="profile-character-save-avatar">${portrait}</div><div class="profile-character-save-copy"><div><strong>${escapeHtml(name)}</strong><span class="status-pill ${character.editable?'online':'unknown'}">${character.editable?'RSDW READY':'PRESERVE ONLY'}</span></div><small>${escapeHtml(character.file_name||'Dragonwilds character save')} · ${escapeHtml(modified)} · ${formatBytes(character.size||0)}</small><div class="profile-character-worlds">${worlds}</div></div><button class="btn primary compact-btn" data-profile-character-editor="${escapeHtml(character.id)}" ${character.editable?'':'disabled'}>Open Character Editor in RSDW-L</button></article>`;
    }).join('');
    return `<div class="content profile-page"><div class="page-header"><div><div class="eyebrow">Profile Management</div><h1>User Profile</h1><div class="page-subtitle">Your Dragonwilds Sync identity, characters, saves, and RSDW-powered tools live together here.</div></div><div class="header-actions"><button class="btn ghost" id="detach-profile">${detachedMode?'↙ Return to Application':'↗ Open in Window'}</button><button class="btn primary" id="edit-profile-page">Edit Profile</button></div></div>${profileTabs()}<section class="profile-page-hero">${banner}<div class="profile-page-shade"></div><div class="profile-page-identity"><div class="profile-page-avatar">${p.avatar_data?avatar:`<span>${avatar}</span>`}</div><div><div class="eyebrow">Dragonwilds Sync Profile</div><h2>${escapeHtml(p.display_name || 'Player')}</h2><p>${escapeHtml(p.about || 'Add an About Me section from Edit Profile.')}</p></div></div></section><div class="profile-overview-grid"><section class="panel"><div class="panel-header"><h2>Profile Summary</h2></div><div class="panel-body"><div class="metric-grid">${metric('Characters', String(characterCount))}${metric('RSDWL', 'v3 Profile')}${metric('Profile', 'Local & portable')}</div></div></section><section class="panel"><div class="panel-header"><div><h2>Socials</h2><span class="panel-subtitle">${escapeHtml(nexusState)}</span></div></div><div class="panel-body"><div class="profile-social-list">${socialRows}</div></div></section></div><section class="panel profile-character-saves"><div class="panel-header"><div><h2>Associated Character Saves</h2><span class="panel-subtitle">World associations and safe RSDW-L editor handoff</span></div><button class="btn ghost compact-btn" data-profile-tab="characters">Open Characters</button></div><div class="panel-body profile-character-save-list">${characterRows||'<div class="empty-state compact"><strong>No Dragonwilds character saves found.</strong><span>Open Settings → Player to confirm the game folder, then return to Profile.</span></div>'}</div></section></div>`;
  }

  function connectionStamp(row) {
    const raw=row?.last_connected_at||row?.last_played_at||row?.last_connected_at_utc||row?.updated_at||0;
    if (typeof raw === 'number' && Number.isFinite(raw)) return raw > 1e12 ? raw : raw * 1000;
    const parsed=Date.parse(String(raw||''));
    return Number.isFinite(parsed) ? parsed : 0;
  }

  function renderCharacterLedgerPane(selected) {
    const characterId=String(selected?.id||'');
    const associated=new Set([...(selected?.world_ids||[]),...(selected?.selected_for_worlds||[])].map(String));
    const belongs=(row)=>String(row?.character_id||'')===characterId || (!row?.character_id && associated.has(String(row?.world_id||'')));
    const connections=(state.data?.client?.recent_connections||[]).filter(belongs).sort((a,b)=>connectionStamp(b)-connectionStamp(a));
    const feedback=(state.data?.player_profile?.feedback_history||[]).filter(belongs);
    const connectionRows=connections.slice(0,100).map((row)=>`<div class="ledger-row"><div><strong>${escapeHtml(row.world_name||rsdwWorldName(row.world_id)||'World')}</strong><small>${escapeHtml(row.external_ip||row.internal_ip||row.source||'Saved World identity')}</small></div><time>${connectionStamp(row)?new Date(connectionStamp(row)).toLocaleString():'Saved'}</time></div>`).join('');
    const feedbackRows=[...feedback].reverse().map((row)=>`<div class="ledger-row"><div><strong>${'★'.repeat(Number(row.rating||0))}${'☆'.repeat(Math.max(0,5-Number(row.rating||0)))} · ${escapeHtml(row.world_name||'World')}</strong><small>${escapeHtml(row.report||'Rating submitted without a written note.')}</small></div><time>${escapeHtml(String(row.submitted_at||''))}</time></div>`).join('');
    return `<div class="profile-overview-grid ledger-grid"><section class="panel"><div class="panel-header"><h2>Connected Worlds</h2></div><div class="panel-body ledger-list">${connectionRows||'<div class="empty-state compact-empty">This character has no World connection history yet.</div>'}</div></section><section class="panel"><div class="panel-header"><h2>Feedback Left</h2></div><div class="panel-body ledger-list">${feedbackRows||'<div class="empty-state compact-empty">This character has not submitted World feedback yet.</div>'}</div></section></div>`;
  }

  function renderCharacterMapPane(selected,payload) {
    return `<section class="panel character-map-panel"><div class="panel-header"><div><h2>${escapeHtml(t('characterMap'))}</h2><span class="panel-subtitle">Last position written into ${escapeHtml(selected?.profile?.label||selected?.player_name||selected?.file_name||'this character')}—not live tracking.</span></div></div><div class="panel-body">${characterLastLocationMarkup(selected,payload)}</div></section>`;
  }

  function renderProfile() {
    if (state.profileTab === 'characters') { state.rsdwSection='character'; return renderRsdwToolkit(); }
    if (!['user','characters'].includes(state.profileTab)) state.profileTab='user';
    return renderUserProfile();
  }

  function nativeSelectOptions(choices, selected) {
    const rows=Array.isArray(choices)?choices:[];
    return rows.map((row)=>`<option value="${escapeHtml(row.value||'')}" ${String(row.value||'')===String(selected||'')?'selected':''}>${escapeHtml(row.label||row.value||'')}</option>`).join('');
  }

  function nativeAppearanceField(editor, key, label) {
    const current=editor?.customization?.[key]||'';
    const choices=editor?.catalog?.[key]||[];
    return `<label class="native-editor-field"><span>${escapeHtml(label)}<small>${choices.length} current RSDW choice${choices.length===1?'':'s'}</small></span><select class="select" data-native-customization="${escapeHtml(key)}">${nativeSelectOptions(choices,current)}</select></label>`;
  }

  function nativeColorField(editor, key, label) {
    const current=editor?.customization?.[key]||'';
    const choices=editor?.catalog?.[key]||[];
    const selected=choices.find((row)=>String(row.value||'')===String(current))||choices[0]||{color:'#888',label:current||label};
    return `<details class="native-pastel-picker"><summary title="Choose ${escapeHtml(label)} color"><span>${escapeHtml(label)}</span><i style="--native-swatch:${escapeHtml(selected.color||'#888')}"></i><small>${escapeHtml(selected.label||selected.value||'Choose')}</small></summary><div class="native-pastel-wheel" role="listbox" aria-label="${escapeHtml(label)} colors">${choices.map((row,index)=>`<label class="native-color-choice ${String(row.value||'')===String(current)?'selected':''}" style="--i:${index};--count:${Math.max(1,choices.length)}" title="${escapeHtml(row.label||row.value||'')}"><input type="radio" name="native-${escapeHtml(key)}" data-native-customization="${escapeHtml(key)}" value="${escapeHtml(row.value||'')}" ${String(row.value||'')===String(current)?'checked':''}/><i style="--native-swatch:${escapeHtml(row.color||'#888')}"></i><span>${escapeHtml(row.label||row.value||'')}</span></label>`).join('')}<b class="native-pastel-thumb" aria-hidden="true">✦</b></div></details>`;
  }

  function nativeAppearanceSelector(editor, key, label) {
    const current=String(editor?.customization?.[key]||'');
    const choices=Array.isArray(editor?.catalog?.[key])?editor.catalog[key]:[];
    const index=Math.max(0,choices.findIndex((row)=>String(row.value||'')===current));
    const selected=choices[index]||{value:current,label:current||'Not surfaced'};
    const raw=String(selected.value||current||'Not surfaced');
    const friendly=String(selected.label||raw);
    return `<section class="character-appearance-card" data-appearance-card="${escapeHtml(key)}"><div class="character-appearance-card-head"><strong>${escapeHtml(label)}</strong><span>${choices.length} save-backed choice${choices.length===1?'':'s'}</span></div><div class="character-appearance-card-body"><div class="character-asset-silhouette" aria-hidden="true"><i></i></div><div class="character-asset-selector"><div class="character-asset-current"><button type="button" data-native-step="${escapeHtml(key)}" data-native-step-delta="-1" ${choices.length<2?'disabled':''} aria-label="Previous ${escapeHtml(label)}">‹</button><span><strong>${escapeHtml(raw)}</strong>${friendly!==raw?`<small>${escapeHtml(friendly)}</small>`:'<small>Authoritative asset name</small>'}</span><button type="button" data-native-step="${escapeHtml(key)}" data-native-step-delta="1" ${choices.length<2?'disabled':''} aria-label="Next ${escapeHtml(label)}">›</button></div><select class="select" data-native-customization="${escapeHtml(key)}" aria-label="Select ${escapeHtml(label)} asset">${nativeSelectOptions(choices,current)}</select><div class="character-asset-range"><input type="range" min="0" max="${Math.max(0,choices.length-1)}" value="${index}" data-native-range="${escapeHtml(key)}" ${choices.length<2?'disabled':''}/><span>${choices.length?index+1:0} / ${choices.length}</span></div></div></div></section>`;
  }

  function characterEquipmentCompatible(row, slot) {
    const text=`${row?.equipment||''} ${row?.category||''} ${row?.name||''} ${row?.description||''} ${row?.item_data||''}`.toLowerCase();
    if(slot==='Main Hand')return /(weapon|weapons|tool|sword|axe|maul|staff|wand|bow|crossbow|pickaxe|dagger|spear|mace)/.test(text)&&!/(shield|off[ -]?hand)/.test(text);
    if(slot==='Off Hand')return /(off[ -]?hand|shield|buckler|focus|orb|weapon|sword|dagger|wand)/.test(text);
    return String(row?.equipment||'')===String(slot||'');
  }

  function characterEquipmentSurface(liveAvatar) {
    const itemEditor=state.rsdwNativeTools['item-editor']||{};
    const repositoryItems=Object.values(itemEditor.tabs||{}).flatMap((tab)=>tab.items||[]);
    const loadout=new Map((itemEditor.sections?.loadout||[]).map((row)=>[Number(row.slot),row]));
    const inventory=new Map((itemEditor.sections?.inventory||[]).map((row)=>[Number(row.slot),row]));
    const socket=(equipment,index)=>{const row=loadout.get(index);const hiddenKey={Head:'helmet',Body:'torso',Legs:'legs',Cape:'cape'}[equipment]||'';const hidden=hiddenKey&&state.rsdwPreviewHidden.has(hiddenKey);return `<button class="studio-equipment-socket character-equipped-row ${row?'occupied':'empty'} ${hidden?'hidden-preview':''}" data-studio-equipment-slot="${escapeHtml(equipment)}" data-studio-equipment-index="${index}" data-studio-equipped-item="${escapeHtml(row?.item_data||'')}" aria-label="${escapeHtml(equipment)} equipment slot · ${escapeHtml(row?.name||'Empty')}" title="Click to browse · Right-click to quick equip ${escapeHtml(equipment)} items">${row?`<img src="${escapeHtml(rsdwAssetUrl(row.icon))}" alt="" loading="lazy"/>`:`<span class="studio-socket-glyph">${escapeHtml(equipment.slice(0,1))}</span>`}<span><strong>${escapeHtml(equipment)}</strong><small>${escapeHtml(row?.name||'Empty slot')}</small><i>${hidden?'Hidden in preview':'Save-backed'}</i></span>${hiddenKey?`<b class="studio-socket-eye ${hidden?'hidden':''}" data-rsdw-socket-eye="${hiddenKey}" title="${hidden?'Show':'Hide'} ${escapeHtml(equipment)} in preview">◉</b>`:''}<em aria-hidden="true">⌕</em></button>`;};
    const hand=(label,slot,upstreamId)=>{const model=liveAvatar?.params?.[slot]||'';const hidden=state.rsdwPreviewHidden.has(slot);const chosen=state.rsdwPreviewWeaponItems?.[slot]||null;const row=chosen||repositoryItems.find((item)=>String(item.item_data||'')===String(model)||(String(item.internal_name||item.name||'')&&String(model).toLowerCase().includes(String(item.internal_name||item.name||'').toLowerCase())));const occupied=!!(model||row);const media=row?.icon?`<img src="${escapeHtml(rsdwAssetUrl(row.icon))}" alt="" loading="lazy"/>`:`<span class="studio-socket-glyph">${label==='Main Hand'?'⚔':'◈'}</span>`;return `<button class="studio-equipment-socket character-equipped-row preview-hand ${occupied?'occupied':'empty'} ${hidden?'hidden-preview':''}" data-studio-equipment-slot="${escapeHtml(label)}" data-avatar-hand-slot="${escapeHtml(upstreamId)}" data-studio-equipped-item="${escapeHtml(row?.item_data||model)}" aria-label="${escapeHtml(label)} slot · ${escapeHtml(row?.name||model||'Empty')}" title="Click to browse · Right-click to change or remove ${escapeHtml(label)} items">${media}<span><strong>${escapeHtml(label)}</strong><small>${escapeHtml(row?.name||(model?String(model).split('/').pop():'Choose preview item'))}</small><i>RSDWModel preview mapping</i></span><b class="studio-socket-eye ${hidden?'hidden':''}" data-rsdw-socket-eye="${slot}" title="${hidden?'Show':'Hide'} ${escapeHtml(label)}">◉</b><em aria-hidden="true">⌕</em></button>`;};
    const hotbar=Array.from({length:8},(_,index)=>{const row=inventory.get(index);return `<button type="button" class="character-action-slot ${row?'occupied':''}" data-character-action-slot="${index}" data-studio-equipped-item="${escapeHtml(row?.item_data||'')}" title="${escapeHtml(row?`${row.name||row.item_data} · quantity ${Number(row.count||1)}`:`Action slot ${index+1} · empty`)}"><b>${index+1}</b>${row?`<img src="${escapeHtml(rsdwAssetUrl(row.icon))}" alt="" loading="lazy"/><span>${Number(row.count||1)>1?escapeHtml(row.count):''}</span>`:'<i aria-hidden="true">＋</i>'}</button>`;}).join('');
    return {right:`<aside class="character-editor-equipped" aria-label="Equipped items"><div class="character-equipped-title"><div><span>Equipped</span><strong>${itemEditor.sections?'Item repository ready':'Loading item repository…'}</strong></div><button type="button" class="btn ghost compact-btn" data-open-item-editor title="Open the full Item Editor">Manage</button></div><section><h4>Armour</h4>${socket('Head',0)}${socket('Body',1)}${socket('Legs',2)}</section><section><h4>Attachments</h4>${socket('Cape',3)}${socket('Jewellery',4)}</section><section><h4>Weapons <small>preview mapped</small></h4>${hand('Main Hand','rightHand','slot-rightHand')}${hand('Off Hand','leftHand','slot-leftHand')}</section></aside>`,hotbar};
  }

  function nativeCharacterEditorMarkup(payload) {
    const editor=(state.rsdwNativeDraft?.native_editor)||payload?.native_editor||{};
    const meta=editor.meta||{};
    const upkeep=editor.upkeep||{};
    const skills=editor.skills||[];
    const mounts=editor.mounts||[];
    const vendors=editor.vendors||[];
    const equipped=editor.equipped_mount||'None';
    const liveAvatar=state.rsdwPreviewAvatar||payload?.avatar||{};
    const avatarUrl=rsdwAvatarUrl(liveAvatar.url);
    const avatarBackground=String(state.rsdwAvatarBackground||'studio');
    const suspendAvatar=hostingFocusActive()&&activeComputerProfile().suspend_visuals!==false;
    const avatarMarkup=suspendAvatar
      ? `<div class="character-preview-paused hosting-focus-placeholder"><strong>Character Preview Paused</strong><p>The live 3D renderer is resting while Hosting Focus is active. Stop the server or disable “Pause 3D previews” in Settings → Application.</p></div>`
      : `<div class="rsdw-avatar-pane character-preview-pane"><div class="rsdw-avatar-stage-shell avatar-loading" style="--avatar-scale:${Number(state.rsdwAvatarScale||62)}vh"><webview id="rsdw-avatar-webview" class="rsdw-avatar-webview" src="${escapeHtml(avatarUrl)}" partition="persist:dragonwilds-rsdw"></webview><div class="rsdw-avatar-loading-cover" aria-live="polite"><div class="spinner"></div><strong>Preparing Character Preview</strong><span>Loading the save-backed 3D renderer…</span></div><div class="rsdw-avatar-toolbar"><button class="btn ghost compact-btn" data-avatar-view="full" title="Full body">Full</button><button class="btn ghost compact-btn" data-avatar-view="face" title="Face view">Face</button><button class="btn ghost compact-btn" data-avatar-view="rotate-left" title="Rotate left">↶</button><button class="btn ghost compact-btn" data-avatar-view="rotate-right" title="Rotate right">↷</button><button class="btn ghost compact-btn" data-avatar-view="zoom-in" title="Zoom in">＋</button><button class="btn ghost compact-btn" data-avatar-view="zoom-out" title="Zoom out">−</button></div><span class="rsdw-avatar-gesture-note">${escapeHtml(et('avatarGestures'))}</span></div><div class="rsdw-avatar-actions"><span id="rsdw-avatar-status">Loading RSDWModel avatar…</span></div></div>`;
    const equipment=characterEquipmentSurface(liveAvatar);
    const dirty=state.rsdwNativeDraft?.characterId===state.characterSelectedId;
    const activeTab=['appearance','pose','background'].includes(state.rsdwCharacterEditorTab)?state.rsdwCharacterEditorTab:'appearance';
    return `<div class="rsdw-native-character-editor character-editor-redesign" id="rsdw-native-character-editor" data-character-editor-active-tab="${activeTab}">
      <header class="character-editor-redesign-head"><div class="character-editor-title"><span>Character Editor</span><strong>${escapeHtml(meta.player_name||'Unnamed Character')}</strong><i class="character-dirty-indicator ${dirty?'dirty':''}" data-character-dirty>${dirty?'Unsaved changes':'Saved'}</i><button type="button" class="btn primary compact-btn character-title-preview-refresh" id="rsdw-see-changes" ${state.rsdwPreviewPending?'':'disabled'}>See changes</button></div><div class="character-editor-tabs" role="tablist" aria-label="Character editor sections">${[['appearance','Appearance'],['pose','Pose'],['background','Background']].map(([key,label])=>`<button type="button" role="tab" data-character-editor-tab="${key}" aria-selected="${activeTab===key}" aria-haspopup="${key==='appearance'?'false':'dialog'}" class="${activeTab===key?'active':''}" title="${key==='appearance'?'Open appearance controls':`Open ${label} controls · right-click for quick chooser`}">${label}${key==='appearance'?'':' ▾'}</button>`).join('')}</div><div class="character-editor-head-actions"><button type="button" class="btn ghost compact-btn" data-character-undo title="Undo last editor change" ${state.rsdwCharacterHistory.length?'':'disabled'}>↶ Undo</button><button type="button" class="btn ghost compact-btn" data-character-redo title="Redo editor change" ${state.rsdwCharacterFuture.length?'':'disabled'}>↷ Redo</button><button type="button" class="btn ghost compact-btn" id="rsdw-revert-draft" ${dirty?'':'disabled'}>Revert</button></div><section class="character-tab-popover character-pose-popover" data-character-tab-popover="pose" role="dialog" aria-label="Pose chooser" hidden><header><div><span>Preview pose</span><strong>RSDWModel animations</strong></div><button type="button" data-character-popover-close aria-label="Close pose chooser">×</button></header><label class="character-popover-search"><span>Filter poses</span><input type="search" data-character-pose-filter placeholder="Filter poses…" autocomplete="off"/></label><div class="character-pose-choice-list" data-character-pose-list><div class="character-popover-empty">Animations are loading from the 3D renderer…</div></div><footer><button type="button" class="btn ghost compact-btn" data-avatar-play="play">▶ Play</button><button type="button" class="btn ghost compact-btn" data-avatar-play="pause">Ⅱ Pause</button><button type="button" class="btn ghost compact-btn" data-avatar-view="full">Reset camera</button></footer></section><section class="character-tab-popover character-background-popover" data-character-tab-popover="background" role="dialog" aria-label="Background chooser" hidden><header><div><span>Preview environment</span><strong>Scenes and solid colors</strong></div><button type="button" data-character-popover-close aria-label="Close background chooser">×</button></header><div class="character-popover-section"><small>Backdrop scenes</small><div class="character-popover-backdrops">${CHARACTER_BACKDROPS.map((backdrop)=>`<button type="button" class="character-background-card ${avatarBackground===backdrop.value?'active':''}" data-character-background-choice="${backdrop.value}" aria-pressed="${avatarBackground===backdrop.value}"><img src="${escapeHtml(characterBackdropUrl(backdrop.value))}" alt="" loading="lazy"/><span>${backdrop.label}</span></button>`).join('')}</div></div><div class="character-popover-section"><small>Solid colors</small><div class="character-background-swatches">${CHARACTER_BACKGROUND_STYLES.map(({value,label,surface:color})=>`<button type="button" class="${avatarBackground===value?'active':''}" data-character-background-choice="${value}" aria-pressed="${avatarBackground===value}" style="--character-background-swatch:${color}"><i></i><span>${label}</span></button>`).join('')}</div></div></section></header>
      <div class="character-editor-workspace">
        <aside class="character-editor-controls">
          <div class="character-editor-tab-panel ${activeTab==='appearance'?'active':''}" data-character-tab-panel="appearance"><label class="character-name-field"><span>Name</span><input class="field" data-native-meta="player_name" maxlength="128" value="${escapeHtml(meta.player_name||'')}"/></label><div class="character-nickname-row"><span>Asset nicknames remain secondary to raw save names.</span><button type="button" disabled title="Nickname metadata is not available in the current save schema">Edit</button></div>${nativeAppearanceSelector(editor,'Head','Face')}${nativeAppearanceSelector(editor,'HairPreset','Hair')}${nativeAppearanceSelector(editor,'FacialHairPreset','Beard')}<div class="character-body-type">${nativeAppearanceField(editor,'BodyType',et('bodyType'))}</div><div class="character-color-rows">${nativeColorField(editor,'SkinTone','Skin')}${nativeColorField(editor,'EyeColor','Eyes')}${nativeColorField(editor,'HairColor','Hair')}${nativeColorField(editor,'EyebrowColor','Beard')}</div></div>
          <div class="character-editor-tab-panel ${activeTab==='pose'?'active':''}" data-character-tab-panel="pose"><div class="character-tab-callout"><span>Pose</span><strong>Preview-only animation</strong><p>Pose and camera changes never modify the character save.</p></div><label class="native-editor-field"><span>Animation<small>RSDWModel catalog</small></span><select class="select" data-avatar-upstream-select="avatar-animation-select" data-avatar-default="idle" disabled><option>Loading animations…</option></select></label><div class="character-pose-actions"><button type="button" class="btn ghost" data-avatar-play="play">▶ Play</button><button type="button" class="btn ghost" data-avatar-play="pause">Ⅱ Pause</button><button type="button" class="btn ghost" data-avatar-view="full">Reset camera</button></div></div>
          <div class="character-editor-tab-panel ${activeTab==='background'?'active':''}" data-character-tab-panel="background"><div class="character-tab-callout"><span>Background</span><strong>Preview environment</strong><p>Choose the 3D viewport backdrop without modifying the character save.</p></div><div class="character-background-control-mount"><label class="character-toolbar-background"><span>Viewport background</span><select class="select" id="rsdw-avatar-background"><optgroup label="Scenes">${CHARACTER_BACKDROPS.map((backdrop)=>`<option value="${backdrop.value}" ${avatarBackground===backdrop.value?'selected':''}>${backdrop.label}</option>`).join('')}</optgroup><optgroup label="Colors and atmospheres">${CHARACTER_BACKGROUND_STYLES.map(({value,label})=>`<option value="${value}" ${avatarBackground===value?'selected':''}>${label}</option>`).join('')}</optgroup></select></label><div class="character-background-gallery" aria-label="Character backdrop scenes">${CHARACTER_BACKDROPS.map((backdrop)=>`<button type="button" class="character-background-card ${avatarBackground===backdrop.value?'active':''}" data-character-background-choice="${backdrop.value}" aria-pressed="${avatarBackground===backdrop.value}"><img src="${escapeHtml(characterBackdropUrl(backdrop.value))}" alt="" loading="lazy"/><span>${backdrop.label}</span></button>`).join('')}</div></div></div>
        </aside>
        <main class="character-editor-preview" aria-label="Live character preview"><div class="character-preview-label"><span>Live 3D preview</span><strong>RSDWModel · save-backed appearance</strong></div>${avatarMarkup}</main>
        ${equipment.right}
      </div>
      <footer class="character-editor-footer"><div class="character-action-bar" aria-label="Eight-slot character action bar">${equipment.hotbar}</div><div class="character-editor-footer-actions"><button type="button" class="btn ghost" data-character-undo ${state.rsdwCharacterHistory.length?'':'disabled'}>↶ Undo</button><button type="button" class="btn ghost" data-character-redo ${state.rsdwCharacterFuture.length?'':'disabled'}>↷ Redo</button><button type="button" class="btn primary character-save-button" data-character-save ${dirty?'':'disabled'}>▣ Save Character</button><button type="button" class="btn ghost" data-character-export>↥ Export</button></div></footer>
      <details class="character-editor-advanced"><summary><span>Advanced save fields</span><small>Character type, GUID, upkeep, progression, mounts, map, and vendors</small></summary><div class="native-editor-grid native-identity-grid">
        <label class="native-editor-field native-character-type-field"><span>${escapeHtml(et('characterType'))}</span><div><img data-native-character-type-icon src="${escapeHtml(rsdwAssetUrl(`/shared/game-ui/Character/${['Standard','Hardcore','Creative','Custom'][Number(meta.character_type)||0]}.png`))}" alt=""/><select class="select" data-native-meta="character_type"><option value="0" ${Number(meta.character_type)===0?'selected':''}>Standard</option><option value="1" ${Number(meta.character_type)===1?'selected':''}>Hardcore</option><option value="2" ${Number(meta.character_type)===2?'selected':''}>Creative</option><option value="3" ${Number(meta.character_type)===3?'selected':''}>Custom</option></select></div></label>
        <label class="native-editor-field native-guid-field"><span>${escapeHtml(et('characterGuid'))}</span><input class="field mono" data-native-meta="guid" maxlength="32" value="${escapeHtml(meta.guid||'')}"/></label>
      </div>
      <section class="native-editor-section"><div class="native-section-heading"><div><div class="eyebrow">${escapeHtml(et('survival'))}</div><h3>${escapeHtml(et('characterUpkeep'))}</h3></div><span>${escapeHtml(et('setValueKeepFull'))}</span></div><div class="native-upkeep-grid">${['Hydration','Sustenance','Endurance'].map((key)=>{const row=upkeep[key]||{};const translated={Hydration:et('hydration'),Sustenance:et('sustenance'),Endurance:et('endurance')}[key]||key;return `<div class="native-upkeep-card"><div><strong>${escapeHtml(translated)}</strong><span>${escapeHtml(row.infinite?et('infiniteDecay'):et('normalDecay'))}</span></div><input class="field" type="number" min="0" max="100" data-native-upkeep-value="${escapeHtml(key)}" value="${escapeHtml(row.value??0)}"/><label class="native-check"><input type="checkbox" data-native-upkeep-infinite="${escapeHtml(key)}" ${row.infinite?'checked':''}/><span>${escapeHtml(et('keepFull'))}</span></label></div>`;}).join('')}</div></section>
      <details class="native-editor-section native-editor-details"><summary><div><div class="eyebrow">${escapeHtml(et('progression'))}</div><h3>${escapeHtml(et('skills'))}</h3></div><span>${skills.length} ${escapeHtml(et('catalogSkills'))}</span></summary><div class="native-skill-grid">${skills.map((row)=>`<label class="native-skill-card"><img src="${escapeHtml(rsdwAssetUrl(row.icon))}" alt="" loading="lazy"/><span>${escapeHtml(row.label||row.id)}</span><small>${escapeHtml(et('experience'))}</small><input class="field" type="number" min="0" step="1" data-native-skill="${escapeHtml(row.id||'')}" value="${escapeHtml(row.xp??0)}"/></label>`).join('')}</div></details>
      <details class="native-editor-section native-editor-details"><summary><div><div class="eyebrow">${escapeHtml(et('travelWorld'))}</div><h3>${escapeHtml(et('mountsMap'))}</h3></div><span>${mounts.filter((row)=>row.unlocked).length} / ${mounts.length} ${escapeHtml(et('mountsUnlocked'))}</span></summary><div class="native-world-controls"><label class="native-editor-field"><span>${escapeHtml(et('equippedMount'))}</span><select class="select" data-native-mount-equipped><option value="None" ${equipped==='None'?'selected':''}>${escapeHtml(et('noMount'))}</option>${mounts.map((row)=>`<option value="${escapeHtml(row.value)}" ${row.value===equipped?'selected':''}>${escapeHtml(row.label)} · ${escapeHtml(row.type)}</option>`).join('')}</select></label><label class="native-check native-map-check"><input type="checkbox" data-native-map-unlocked ${editor.map_unlocked?'checked':''}/><span><strong>${escapeHtml(et('revealMap'))}</strong><small>${escapeHtml(et('oneWayUnlock'))}</small></span></label></div><div class="native-mount-grid">${mounts.map((row)=>`<label class="native-mount-card"><img src="${escapeHtml(rsdwAssetUrl(row.icon))}" alt="" loading="lazy"/><input type="checkbox" data-native-mount="${escapeHtml(row.value)}" ${row.unlocked?'checked':''}/><span><strong>${escapeHtml(row.label)}</strong><small>${escapeHtml(row.type)}</small></span></label>`).join('')}</div></details>
      <details class="native-editor-section native-editor-details"><summary><div><div class="eyebrow">${escapeHtml(et('reputation'))}</div><h3>${escapeHtml(et('vendors'))}</h3></div><span>${vendors.length} ${escapeHtml(et('currentVendors'))}</span></summary><div class="native-vendor-grid">${vendors.map((row)=>`<label class="native-editor-field"><span>${escapeHtml(row.label)}</span><input class="field" type="number" min="0" step="1" data-native-vendor="${escapeHtml(row.tag)}" value="${escapeHtml(row.amount??0)}"/><small>${escapeHtml(et('tiers'))}: ${(row.tiers||[]).map((tier)=>escapeHtml(tier)).join(' · ')}</small></label>`).join('')}</div></details>
      <div class="native-editor-provenance"><span>${escapeHtml(et('suppliesFields'))}</span><strong>${escapeHtml(et('suppliesUi'))}</strong></div></details>
    </div>`;
  }

  function nativeCatalogToolbar(label, shown, total) {
    return `<div class="native-catalog-toolbar"><label><span>⌕</span><input class="field" id="native-tool-search" value="${escapeHtml(state.rsdwToolSearch||'')}" placeholder="${escapeHtml(et('search'))} ${escapeHtml(label.toLowerCase())}…"/></label><button class="btn ghost compact-btn" id="native-tool-search-apply">${escapeHtml(et('search'))}</button><small>${Number(shown).toLocaleString()} ${escapeHtml(et('of'))} ${Number(total).toLocaleString()}</small></div>`;
  }

  function nativePageDots(pageCount, currentPage) {
    if (pageCount <= 1) return '';
    const wanted=new Set([0,pageCount-1]);
    for(let index=Math.max(0,currentPage-3);index<=Math.min(pageCount-1,currentPage+3);index++)wanted.add(index);
    const pages=[...wanted].sort((a,b)=>a-b);let previous=-2;
    return pages.map((index)=>{const gap=index>previous+1?'<span class="native-page-gap" aria-hidden="true">…</span>':'';previous=index;return `${gap}<button class="${index===currentPage?'active':''}" data-native-page="${index}" title="${escapeHtml(et('page'))} ${index+1}"></button>`;}).join('');
  }

  const RSDW_ITEM_TABS={
    bag:{labelKey:'bagItems',offset:8,customIcon:'assets/rsdw-toolkit/bag-items.svg'},
    rune:{labelKey:'runeItems',offset:32,customIcon:'assets/rsdw-toolkit/rune-items.svg'},
    ammo:{labelKey:'ammoItems',offset:56,customIcon:'assets/rsdw-toolkit/ammo-items.svg'},
    quest:{labelKey:'questItems',offset:80,customIcon:'assets/rsdw-toolkit/quest-items.svg'},
    custom:{labelKey:'moddedItems',offset:8,customIcon:'assets/rsdw-toolkit/modded-items.svg'},
    unrecognized:{labelKey:'unrecognizedItems',offset:8,customIcon:'assets/rsdw-toolkit/modded-items.svg'},
  };
  const RSDW_BAG_CATEGORIES=[
    ['Armour','Armour_Normal.png','Armour_Selected.png'],['Consumables','Consumables_Normal.png','Consumables_Selected.png'],
    ['Materials','Materials_Normal.png','Materials_Selected.png'],['Tools','Tools_Normal.png','Tools_Selected.png'],
    ['Weapons','Weapons_Normal.png','Weapons_Selected.png'],['Plans','Plans_Vestiges_Normal.png','Plans_Vestiges_Selected.png'],
  ];
  const RSDW_LOADOUT_SLOTS=[['Head','Head.png'],['Body','Body.png'],['Legs','Legs.png'],['Cape','Cape.png'],['Jewellery','Jewellery.png']];

  function nativeItemSlot(row,{section,slot,kind='storage',tab='',equipment='',overlay=''}={}) {
    const occupied=!!row;
    const title=occupied?`${row.name||row.item_data} · ${et('quantity')} ${Number(row.count||1)}`:et('emptySlot');
    return `<div class="native-item-slot ${occupied?'occupied':''} ${row?.custom?'custom-item-fingerprint':''} native-item-slot-${escapeHtml(kind)}" role="button" tabindex="0" title="${escapeHtml(title)}" data-native-item-slot data-section="${escapeHtml(section)}" data-slot="${Number(slot)}" data-kind="${escapeHtml(kind)}" data-tab="${escapeHtml(tab)}" data-equipment="${escapeHtml(equipment)}" data-item-data="${escapeHtml(row?.item_data||'')}" data-item-name="${escapeHtml(row?.name||'')}" data-item-count="${Number(row?.count||1)}" data-item-equipment="${escapeHtml(row?.equipment||'')}" data-item-recognized="${row?.recognized===false?'0':'1'}" data-item-custom="${row?.custom?'1':'0'}" data-base-durability="${row?.base_durability==null?'':escapeHtml(row.base_durability)}" draggable="${occupied?'true':'false'}">${overlay?`<img class="native-slot-overlay" src="${escapeHtml(rsdwAssetUrl(`/shared/game-ui/ItemBrowser/EquipmentSlots/${overlay}`))}" alt="${escapeHtml(equipment)}"/>`:''}${occupied?`<img class="native-slot-icon" src="${escapeHtml(row.icon?rsdwAssetUrl(row.icon):'assets/rsdw-toolkit/modded-items.svg')}" alt="" loading="lazy"/><b>${Number(row.count||1)>1?escapeHtml(row.count):''}</b><span>${escapeHtml(row.name||'')}</span>`:''}</div>`;
  }

  function nativeItemEditorMarkup(editor) {
    const tabs=editor?.tabs||{};
    const tabKey=tabs[state.rsdwItemCatalogTab]?state.rsdwItemCatalogTab:(Object.keys(tabs)[0]||'bag');
    const tab=tabs[tabKey]||{label:'Items',items:[]};
    const query=String(state.rsdwToolSearch||'').trim().toLowerCase();
    const category=tabKey==='bag'?String(state.rsdwItemBagCategory||''):'';
    const filtered=(tab.items||[]).filter((row)=>(!category||String(row.category||'').split('/')[0]===category)&&(!query||`${row.name||''} ${row.category||''} ${row.description||''}`.toLowerCase().includes(query)));
    const pageSize=40;const pageCount=Math.max(1,Math.ceil(filtered.length/pageSize));const page=Math.max(0,Math.min(Number(state.rsdwToolPage||0),pageCount-1));const visible=filtered.slice(page*pageSize,(page+1)*pageSize);
    const inventoryRows=editor?.sections?.inventory||[];const personalRows=editor?.sections?.personal||[];const loadoutRows=editor?.sections?.loadout||[];
    const inventory=new Map(inventoryRows.map((row)=>[Number(row.slot),row]));const personal=new Map(personalRows.map((row)=>[Number(row.slot),row]));const loadout=new Map(loadoutRows.map((row)=>[Number(row.slot),row]));
    const offset=RSDW_ITEM_TABS[tabKey]?.offset??8;
    const catalogSlotCount=Math.max(8,Math.ceil(Math.max(visible.length,1)/8)*8);
    const catalogSlots=Array.from({length:catalogSlotCount},(_,index)=>{const row=visible[index];return `<div class="native-browser-slot ${row?'occupied':''} ${row?.custom?'custom-item-fingerprint':''}" role="button" tabindex="0" title="${escapeHtml(row?`${row.name} · ${row.category||'Item'}${row.custom?' · Custom item':''}`:et('emptySlot'))}" data-native-catalog-slot data-item-data="${escapeHtml(row?.item_data||'')}" data-item-name="${escapeHtml(row?.name||'')}" data-item-equipment="${escapeHtml(row?.equipment||'')}" data-item-max="${Number(row?.max_stack||1)}" data-item-unknown="${row?.unknown?'1':'0'}" data-item-custom="${row?.custom?'1':'0'}" draggable="${row?'true':'false'}">${row?`<img src="${escapeHtml(row.icon?rsdwAssetUrl(row.icon):'assets/rsdw-toolkit/modded-items.svg')}" alt="" loading="lazy"/><span>${escapeHtml(row.name)}</span>`:''}</div>`;}).join('');
    const actionSlots=Array.from({length:8},(_,index)=>nativeItemSlot(inventory.get(index),{section:'inventory',slot:index,kind:'action',tab:'bag'})).join('');
    const categorySlots=Array.from({length:24},(_,index)=>nativeItemSlot(inventory.get(offset+index),{section:'inventory',slot:offset+index,kind:'tabbed',tab:tabKey})).join('');
    const personalSlots=Array.from({length:80},(_,index)=>nativeItemSlot(personal.get(index),{section:'personal',slot:index,kind:'personal',tab:'bag'})).join('');
    const equipmentSlots=RSDW_LOADOUT_SLOTS.map(([equipment,overlay],index)=>nativeItemSlot(loadout.get(index),{section:'loadout',slot:index,kind:'loadout',tab:'bag',equipment,overlay})).join('');
    const allCatalog=Object.values(tabs).reduce((sum,row)=>sum+(row.items||[]).length,0);
    const repositoryOpen=state.rsdwItemRepositoryOpen!==false;
    const tabButton=(key)=>{const cfg=RSDW_ITEM_TABS[key]||RSDW_ITEM_TABS.bag;const label=key==='custom'?'Uncategorized / Modded':key==='unrecognized'?'Unrecognized Items':et(cfg.labelKey);const icon=cfg.customIcon?cfg.customIcon:rsdwAssetUrl(`/shared/game-ui/Inventory/${tabKey===key?cfg.selected:cfg.normal}`);return `<button class="inventory-category-tab ${tabKey===key?'active':''}" data-native-item-tab="${escapeHtml(key)}" title="${escapeHtml(label)}" aria-label="${escapeHtml(label)}"><img src="${escapeHtml(icon)}" alt=""/><span>${escapeHtml(label)}</span></button>`;};
    const standardTabs=['bag','ammo','quest'].filter((key)=>tabs[key]).map(tabButton).join('');
    const specialTabs=['rune','custom','unrecognized'].filter((key)=>tabs[key]).map(tabButton).join('');
    return `<div class="rsdw-native-tool-editor native-item-editor" data-native-tool-host="item-editor"><div class="native-rsdw-inventory-layout ${repositoryOpen?'repository-open':'repository-closed'}">
      <section class="native-rsdw-item-browser"><div class="native-rsdw-panel-title"><img src="${escapeHtml(rsdwAssetUrl('/shared/game-ui/ItemBrowser/ItemBrowser.png'))}" alt=""/><span>${escapeHtml(et('itemBrowser'))}</span></div><h3>${escapeHtml(tabKey==='custom'?'Uncategorized / Modded':tabKey==='unrecognized'?'Unrecognized Items':et(RSDW_ITEM_TABS[tabKey]?.labelKey||'bagItems'))}</h3>
        <div class="native-item-search"><span>⌕</span><input class="field" id="native-tool-search" value="${escapeHtml(state.rsdwToolSearch||'')}" placeholder="${escapeHtml(et('searchItems'))}"/><button class="btn ghost compact-btn" id="native-tool-search-apply">${escapeHtml(et('search'))}</button></div>
        ${tabKey==='bag'?`<div class="native-bag-categories">${RSDW_BAG_CATEGORIES.map(([key,normal,selected])=>`<button class="${category===key?'active':''}" data-native-bag-category="${escapeHtml(key)}" title="${escapeHtml(key)}"><img src="${escapeHtml(rsdwAssetUrl(`/shared/game-ui/ItemBrowser/BagTabCategories/${category===key?selected:normal}`))}" alt="${escapeHtml(key)}"/></button>`).join('')}</div>`:''}
        <div class="native-browser-scroller"><button class="native-grid-arrow" data-native-page="${page-1}" ${page<=0?'disabled':''} aria-label="${escapeHtml(et('previous'))}">‹</button><div class="native-browser-grid">${catalogSlots}</div><button class="native-grid-arrow" data-native-page="${page+1}" ${page>=pageCount-1?'disabled':''} aria-label="${escapeHtml(et('next'))}">›</button></div>
        <div class="native-page-dots">${nativePageDots(pageCount,page)}</div><small class="native-browser-count">${visible.length.toLocaleString()} ${escapeHtml(et('of'))} ${filtered.length.toLocaleString()} · ${allCatalog.toLocaleString()} RSDW</small>
      </section>
      <section class="native-rsdw-player-inventory"><div class="native-rsdw-panel-title"><img src="${escapeHtml(rsdwAssetUrl('/shared/game-ui/ItemBrowser/Player.png'))}" alt=""/><span>${escapeHtml(et('playerInventory'))}</span><small>${escapeHtml(et('rightClick'))}</small><button type="button" class="btn ghost compact-btn repository-toggle" id="toggle-item-repository" aria-pressed="${repositoryOpen}">${repositoryOpen?'Hide':'Show'} Item Repository</button></div>
        <div class="native-inventory-flow"><div class="native-storage-tabs inventory-mode-tabs" role="tablist" aria-label="Storage location"><button class="${state.rsdwInventorySection==='inventory'?'active':''}" data-native-inventory-section="inventory"><span class="inventory-tab-glyph">▦</span><span>${escapeHtml(et('playerInventory'))}</span></button><button class="${state.rsdwInventorySection==='personal'?'active':''}" data-native-inventory-section="personal"><img src="${escapeHtml(rsdwAssetUrl('/shared/game-ui/Inventory/PersonalTab.png'))}" alt=""/><span>${escapeHtml(et('personalStorage'))}</span></button></div>${state.rsdwInventorySection==='inventory'?`<div class="native-item-family-groups"><div class="native-item-family standard"><small>Item Categories</small><div>${standardTabs}</div></div><div class="native-item-family special"><small>Uncategorized / Modded</small><div>${specialTabs}</div></div></div>`:''}</div>
        ${state.rsdwInventorySection==='personal'?`<div class="native-inventory-band personal"><label>${escapeHtml(et('personalStorage'))}</label><div class="native-inventory-grid personal eighty">${personalSlots}</div></div>`:`<div class="native-inventory-band equipment-line"><label>${escapeHtml(et('equipment'))}</label><div class="native-inventory-grid equipment">${equipmentSlots}</div></div><div class="native-inventory-band"><label>${escapeHtml(et('actionBar'))}</label><div class="native-inventory-grid action">${actionSlots}</div></div><div class="native-inventory-grid tabbed">${categorySlots}</div>${tabKey==='custom'?`<div class="custom-item-repository-actions"><button class="btn primary compact-btn" id="open-custom-item-repository">＋ Create / Manage Modded Items</button><span>${(tabs.custom?.items||[]).length} definitions can be exported as a portable mod manifest.</span></div>`:''}`}
      </section>
    </div><div class="native-item-context-menu" id="native-item-context-menu" hidden><button data-native-context-action="change">Change / Replace…</button><button data-native-context-action="define">Define / Edit Item</button><button data-native-context-action="rename">Rename Custom Item</button><button data-native-context-action="write-mod">Write to Mod…</button><button data-native-context-action="add">${escapeHtml(et('add'))}</button><button data-native-context-action="add-max">${escapeHtml(et('addMax'))}</button><button data-native-context-action="max">${escapeHtml(et('setMax'))}</button><button data-native-context-action="duplicate">${escapeHtml(et('duplicate'))}</button><button data-native-context-action="custom">${escapeHtml(et('customAmount'))}</button><button data-native-context-action="repair">${escapeHtml(et('repair'))}</button><button data-native-context-action="remove">${escapeHtml(et('remove'))}</button></div></div>`;
  }

  function nativeSpellEditorMarkup(editor) {
    const selected=new Set((editor?.selected||[]).filter(Boolean));
    const catalog=editor?.catalog||[];
    const query=String(state.rsdwToolSearch||'').trim().toLowerCase();
    const filtered=catalog.filter((row)=>!query||`${row.display_name||''} ${row.internal_name||''} ${row.requirements||''}`.toLowerCase().includes(query));
    const catalogPageSize=20;const catalogPages=Math.max(1,Math.ceil(filtered.length/catalogPageSize));const catalogPage=Math.max(0,Math.min(Number(state.rsdwToolPage||0),catalogPages-1));const visible=filtered.slice(catalogPage*catalogPageSize,(catalogPage+1)*catalogPageSize);
    const assigned=state.rsdwSpellWheel.length?state.rsdwSpellWheel:(editor?.selected||[]).slice(0,48);
    const spellPage=Math.max(0,Math.min(Number(state.rsdwSpellPage||0),5));const pageOffset=spellPage*8;
    const wheel=Array.from({length:8},(_,index)=>{const absolute=pageOffset+index;const id=assigned[absolute]||'';const row=catalog.find((entry)=>String(entry.persistence_id||'')===String(id));return `<button class="spell-wheel-slot slot-${index} ${row?'occupied':''}" data-spell-wheel-slot="${absolute}" aria-label="Spellbook page ${spellPage+1}, slot ${index+1}${row?` · ${escapeHtml(row.display_name||row.internal_name||'Spell')}`:''}" title="${row?'Right-click to clear':'Drop an unlocked spell'}">${row?`<img src="${escapeHtml(rsdwAssetUrl(row.spell_icon))}" alt=""/><b>${escapeHtml(row.display_name||row.internal_name||'Spell')}</b>`:`<span>${index+1}</span>`}</button>`;}).join('');
    const spellPages=`<div class="spellbook-pages" aria-label="Spellbook pages">${Array.from({length:6},(_,index)=>`<button class="${index===spellPage?'active':''}" data-spellbook-page="${index}">${index+1}</button>`).join('')}</div>`;
    const catalogNav=`<div class="native-page-dots">${Array.from({length:catalogPages},(_,index)=>`<button class="${index===catalogPage?'active':''}" data-native-page="${index}" title="${escapeHtml(et('page'))} ${index+1}"></button>`).join('')}</div>`;
    return `<div class="rsdw-native-tool-editor native-spell-editor" data-native-tool-host="spell-editor"><section class="native-editor-section native-spellbook-section"><div class="native-section-heading"><div><div class="eyebrow">RSDW Spellbook</div><h3>Spellbook · Page ${spellPage+1} of 6</h3></div><span>${selected.size} / 48 ${escapeHtml(et('spellbookUsed'))}</span></div>${spellPages}<div class="native-spell-wheel-shell" style="--rsdw-spellbook-bg:url('${escapeHtml(rsdwAssetUrl('/tools/spell-editor/assets/T_Radial_Base_Bg.png'))}')"><div class="native-spell-wheel" aria-label="Spellbook page ${spellPage+1}">${wheel}<div class="spell-wheel-center"><button data-spellbook-page="${Math.max(0,spellPage-1)}" ${spellPage===0?'disabled':''} aria-label="Previous spellbook page">‹</button><span><strong>PAGE</strong><b>${spellPage+1} / 6</b></span><button data-spellbook-page="${Math.min(5,spellPage+1)}" ${spellPage===5?'disabled':''} aria-label="Next spellbook page">›</button></div></div></div><p class="muted-small">Drag an unlocked spell onto a rune socket. Right-click a socket to clear it; use the center arrows to turn pages.</p>${nativeCatalogToolbar(et('spellEditor'),filtered.length,catalog.length)}<div class="native-spell-grid">${visible.map((row)=>{const id=String(row.persistence_id||'');const unlocked=(editor?.unlocked||[]).includes(id);const active=selected.has(id);return `<label class="native-spell-card ${active?'active':''} ${unlocked?'unlocked':'locked'}" draggable="${unlocked?'true':'false'}" data-spell-drag="${escapeHtml(id)}"><input type="checkbox" data-native-tool-toggle="spell-editor" value="${escapeHtml(id)}" ${active?'checked':''}/><div class="native-spell-icon"><img src="${escapeHtml(rsdwAssetUrl(row.spell_icon))}" alt="" loading="lazy"/></div><strong>${escapeHtml(row.display_name||row.internal_name||'Spell')}</strong><small>${unlocked?'Unlocked':'Locked'}${row.cooldown!=null?` · ${escapeHtml(row.cooldown)}s cooldown`:''}${row.requirements?` · ${escapeHtml(row.requirements)}`:''}</small><div class="native-spell-costs">${(row.costs||[]).map((cost)=>`<span title="${escapeHtml(cost.display_name||cost.item_id)}"><img src="${escapeHtml(rsdwAssetUrl(cost.icon))}" alt=""/><b>${escapeHtml(cost.count||0)}</b></span>`).join('')}</div></label>`;}).join('')}</div>${catalogNav}</section></div>`;
  }

  function nativeRecipeEditorMarkup(editor) {
    const catalog=editor?.catalog||[];const classify=(row)=>String(row.category||'other');const query=String(state.rsdwToolSearch||'').trim().toLowerCase();const filtered=catalog.filter((row)=>(state.rsdwRecipeCategory==='all'||classify(row)===state.rsdwRecipeCategory)&&(!query||`${row.name||''} ${row.internal_name||''} ${row.station||''} ${(row.created_items||[]).join(' ')}`.toLowerCase().includes(query)));const pageSize=60;const pageCount=Math.max(1,Math.ceil(filtered.length/pageSize));const page=Math.max(0,Math.min(Number(state.rsdwToolPage||0),pageCount-1));const visible=filtered.slice(page*pageSize,(page+1)*pageSize);const counts=catalog.reduce((out,row)=>{const key=classify(row);out[key]=(out[key]||0)+1;return out;},{});const categories=[['all','All'],['equipment','Equipment'],['building','Building'],['consumables','Consumables'],['ammunition','Ammunition'],['materials','Materials'],['other','Other / Unclassified']];
    return `<div class="rsdw-native-tool-editor" data-native-tool-host="recipe-unlocker"><section class="native-editor-section"><div class="native-section-heading"><div><div class="eyebrow">RSDW ${escapeHtml(et('recipes'))}</div><h3>${escapeHtml(et('recipes'))}</h3></div><span>${Number(editor?.unlocked_count||0).toLocaleString()} ${escapeHtml(et('unlocked'))} · ${catalog.length.toLocaleString()} ${escapeHtml(et('available'))}</span></div><div class="native-recipe-categories">${categories.map(([id,label])=>`<button class="btn ${state.rsdwRecipeCategory===id?'primary':'ghost'} compact-btn" data-recipe-category="${id}">${label}<span>${id==='all'?catalog.length:Number(counts[id]||0)}</span></button>`).join('')}</div>${nativeCatalogToolbar(et('recipes'),visible.length,filtered.length)}<div class="native-unlock-grid">${visible.map((row)=>`<label class="native-unlock-card ${row.unlocked?'active':''}"><input type="checkbox" data-native-tool-toggle="recipe-unlocker" value="${escapeHtml(row.id)}" ${row.unlocked?'checked':''}/><div class="native-rsdw-icon-frame"><img src="${escapeHtml(rsdwAssetUrl(row.icon))}" alt="" loading="lazy"/></div><span><strong>${escapeHtml(row.name)}</strong><small>${escapeHtml(row.category||'other')} · ${escapeHtml(row.station||row.internal_name)}</small></span></label>`).join('')}</div>${pageCount>1?`<div class="native-catalog-pagination"><button class="btn ghost compact-btn" data-native-page="${page-1}" ${page<=0?'disabled':''}>${escapeHtml(et('previous'))}</button><span>${escapeHtml(et('page'))} ${page+1} ${escapeHtml(et('of'))} ${pageCount}</span><button class="btn ghost compact-btn" data-native-page="${page+1}" ${page>=pageCount-1?'disabled':''}>${escapeHtml(et('next'))}</button></div>`:''}</section></div>`;
  }

  function nativeQuestEditorMarkup(editor) {
    const catalog=editor?.catalog||[];const query=String(state.rsdwToolSearch||'').trim().toLowerCase();const visible=catalog.filter((row)=>!query||`${row.name||''} ${row.internal_name||''} ${row.region||''}`.toLowerCase().includes(query));
    const group=(rows,label)=>`<div class="native-quest-group"><h4>${escapeHtml(label)}</h4>${rows.map((row)=>`<label class="native-quest-card ${row.completed?'active':''}"><input type="checkbox" data-native-tool-toggle="quest-editor" value="${escapeHtml(row.id)}" ${row.completed?'checked':''}/><img src="${escapeHtml(rsdwAssetUrl('/shared/game-ui/Status/status_loaded_icon.png'))}" alt=""/><span><strong>${escapeHtml(row.name)}</strong><small>${escapeHtml(row.internal_name)}${row.region?` · ${escapeHtml(row.region)}`:''}</small></span><b>${escapeHtml(row.completed?et('complete'):et('incomplete'))}</b></label>`).join('')}</div>`;
    return `<div class="rsdw-native-tool-editor" data-native-tool-host="quest-editor"><section class="native-editor-section"><div class="native-section-heading"><div><div class="eyebrow">RSDW ${escapeHtml(et('questEditor'))}</div><h3>${escapeHtml(et('questCompletion'))}</h3></div><span>${Number(editor?.completed_count||0)} ${escapeHtml(et('complete'))} · ${catalog.length} ${escapeHtml(et('known'))}</span></div>${nativeCatalogToolbar(et('questEditor'),visible.length,catalog.length)}<div class="native-quest-columns">${group(visible.filter((row)=>row.main),et('mainQuests'))}${group(visible.filter((row)=>!row.main),et('sideQuests'))}</div></section></div>`;
  }

  function nativeRsdwToolMarkup(toolId, editor) {
    if(toolId==='item-editor')return nativeItemEditorMarkup(editor);
    if(toolId==='spell-editor')return nativeSpellEditorMarkup(editor);
    if(toolId==='recipe-unlocker')return nativeRecipeEditorMarkup(editor);
    if(toolId==='quest-editor')return nativeQuestEditorMarkup(editor);
    return '';
  }

  function rsdwEditorSurfaceMarkup(selected, payload, tool, { popup = false } = {}) {
    const sourceLocal = state.rsdwSource?.mode === 'local';
    const sourceBadge = sourceLocal ? `<span class="status-pill online">LOCAL · ${escapeHtml((state.rsdwSource.revision||'').slice(0,8) || 'CACHED')}</span>` : '<span class="status-pill unknown">OFFICIAL WEB FALLBACK</span>';
    const charName = selected?.profile?.label || selected?.player_name || selected?.file_name || 'Character';
    if (!selected?.editable || !payload) return `<section class="rsdw-editor-panel ${popup?'popup-editor':''}"><div class="warning-box"><strong>${selected?.editable?'Character hydration unavailable':'Preserve-only character'}</strong><br/>${escapeHtml(state.rsdwHydrationError || selected?.viewer_note || 'This character cannot be safely opened in the RSDW editor surface.')}</div></section>`;
    const nativeCharacter=tool.id==='character-editor'&&payload.native_editor;
    const nativeTool=tool.id!=='character-editor'?state.rsdwNativeTools[tool.id]:null;
    const nativeReady=!!(nativeCharacter||nativeTool);
    const progress=Math.max(8,Number(state.rsdwNativeToolProgress||12));
    const editorBody=nativeCharacter?nativeCharacterEditorMarkup(payload):(nativeTool?nativeRsdwToolMarkup(tool.id,nativeTool):`<div class="native-editor-loading"><div class="spinner"></div><strong>${escapeHtml(et('hydrating'))} ${escapeHtml(tool.label)}</strong><span>${escapeHtml(et('loadingCatalog'))}</span><div class="subapp-progress" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${progress}"><i style="width:${progress}%"></i></div></div>`);
    return `<section class="rsdw-editor-panel ${popup?'popup-editor':''} ${nativeReady?'native-character-surface native-rsdw-tool-surface':''}" data-rsdw-native-tool="${escapeHtml(tool.id)}"><div class="panel-header"><div><div class="eyebrow">RSDW Tools · ${escapeHtml(tool.label)}</div><h2>${escapeHtml(tool.label)}</h2><span class="panel-subtitle">${escapeHtml(charName)} ${escapeHtml(et('loadedAutomatically'))}</span></div>${sourceBadge}</div><div class="rsdw-native-editorbar"><div><i id="rsdw-editor-status-dot" class="${nativeReady?'ready':''}"></i><span id="rsdw-editor-status">${nativeReady?escapeHtml(et('readyNative')):`${escapeHtml(et('loading'))} ${escapeHtml(charName)}…`}</span></div><span class="rsdw-editor-shortcut">Ctrl+S</span><button class="btn primary compact-btn" id="rsdw-save-character" ${state.rsdwNativeDraft?.characterId===selected.id?'':'disabled'}>${escapeHtml(et('saveCharacter'))}</button></div>${editorBody}</section>`;
  }

  function renderRsdwEditorWindow() {
    const chars = state.characters || [];
    const selected = chars.find((character)=>character.id===state.characterSelectedId) || chars[0] || null;
    const payload = selected?.id === state.characterSelectedId ? state.rsdwCharacterPayload : null;
    const tool = translatedRsdwTool(RSDW_TOOLS.find((entry)=>entry.id===state.rsdwTool) || RSDW_TOOLS[0]);
    const toolNav = `<div class="rsdw-tool-nav rsdw-popup-tool-nav">${RSDW_TOOLS.map((rawEntry)=>{const entry=translatedRsdwTool(rawEntry);return `<button class="rsdw-tool-tile ${tool.id===entry.id?'active':''}" data-rsdw-tool="${entry.id}" title="${escapeHtml(entry.label)}"><img src="${entry.icon}" alt=""/><span><strong>${escapeHtml(entry.label)}</strong><small>${escapeHtml(entry.subtitle)}</small></span></button>`;}).join('')}</div>`;
    return `<div class="content rsdw-editor-window"><div class="page-header compact-page-header"><div><div class="eyebrow">Character Editor Window</div><h1>${escapeHtml(tool.label)}</h1><div class="page-subtitle">A full-size RSDW editor for ${escapeHtml(selected?.profile?.label||selected?.player_name||'the selected character')}.</div></div></div>${toolNav}${rsdwEditorSurfaceMarkup(selected,payload,tool,{popup:true})}</div>`;
  }

  function playerMapPanelMarkup(world, { includeSetup = false, toolkit = false } = {}) {
    if (!world) return `<div class="empty-state"><strong>No dedicated World profiles are available.</strong><span>RSDW live tracking appears here when a hosted World is configured. Private World tracking can use the same RSDW telemetry surface when the local game exposes it.</span></div>`;
    const tracker = state.serverPlayers[world.id] || { players: [] };
    const mapCfg = state.serverMapConfig[world.id] || world.player_map || {};
    const mapBg = b64Image(mapCfg.background_data || '');
    const cal = mapCfg.calibration || state.mapOverlays?.calibration || {};
    const title = toolkit ? 'RSDW Live Player Map' : 'Ashenfall Player Map';
    const bridgeAvailable = !!tracker.bridge?.available;
    const sourceCopy = tracker.tracker_connected ? 'RSDW DevKit bridge telemetry · live positions' : (bridgeAvailable ? 'RSDW DevKit bridge detected · waiting for roster' : 'RSDW DevKit bridge not detected · log presence fallback');
    const overlayCategories = Object.keys(state.mapOverlays?.categories || {});
    const coordinateSource=String(mapCfg.coordinate_source||state.mapCacheStatus?.coordinate_source||'');
    const overlaysAligned = coordinateSource==='manual-calibration' || coordinateSource.includes('world-grid') || String(state.mapCacheStatus?.source_provider||'')==='rsdwarchive';
    const playerRows=objectRows(tracker.players);
    const overlayRows=objectRows(state.mapOverlays?.points);
    const playersOnMap = overlaysAligned ? playerRows.filter((pl) => pl.map_point&&typeof pl.map_point==='object') : [];
    const visibleOverlayPoints = overlaysAligned ? overlayRows.filter((point)=>state.mapOverlayFilters.has(point.category)).slice(0, 600) : [];
    const overlayCounts=new Map();overlayRows.forEach((point)=>overlayCounts.set(point.category,(overlayCounts.get(point.category)||0)+1));
    const overlayFilters = overlayCategories.length ? `<div class="map-filter-bar"><div><strong>Map filters</strong><small>RSDW game-data locations · ${Number(state.mapOverlays?.source_point_count || 0).toLocaleString()} indexed</small></div><div class="map-filter-chips">${overlayCategories.map((category)=>{const count=overlayCounts.get(category)||0;return `<button type="button" class="map-filter-chip ${state.mapOverlayFilters.has(category)?'active':''}" data-map-overlay-category="${escapeHtml(category)}"><i class="${escapeHtml(category.toLowerCase())}"></i>${escapeHtml(category)} <b>${count.toLocaleString()}</b></button>`;}).join('')}<button type="button" class="map-filter-chip" data-map-overlay-preset="all">All</button><button type="button" class="map-filter-chip" data-map-overlay-preset="none">None</button></div></div>` : '<div class="map-filter-loading">Resource and location filters load from the cached RSDW game-data index.</div>';
    const overlayMarkers = visibleOverlayPoints.map((point)=>`<i class="map-overlay-marker ${escapeHtml(String(point.category||'').toLowerCase())}" data-map-x="${Number(point.map_x)}" data-map-y="${Number(point.map_y)}" style="left:${Number(point.map_x)*100}%;top:${Number(point.map_y)*100}%" title="${escapeHtml(point.subtype || point.label || point.category || 'Map location')}"></i>`).join('');
    const viewport = state.mapViewports[world.id] || { scale:1, x:0, y:0 };
    const categoryDetails=overlayCategories.map((category)=>{const points=overlayRows.filter((point)=>point.category===category);const types=new Map();points.forEach((point)=>types.set(point.subtype||point.label||category,(types.get(point.subtype||point.label||category)||0)+1));return `<details class="map-data-category"><summary><strong>${escapeHtml(category)}</strong><span>${points.length.toLocaleString()} indexed</span></summary><div>${[...types.entries()].sort((a,b)=>b[1]-a[1]).slice(0,24).map(([label,count])=>`<span>${escapeHtml(label)} <b>${count.toLocaleString()}</b></span>`).join('')}</div></details>`;}).join('');
    const mapPanel = `<details class="panel collapsible-panel map-panel" open><summary class="panel-header"><div><h2>${title}</h2><span class="panel-subtitle">${tracker.player_count || 0} online · ${sourceCopy}</span></div><span class="status-pill ${tracker.tracker_connected ? 'online' : 'unknown'}">${tracker.tracker_connected ? 'RSDW TRACKING LIVE' : 'TRACKING OFFLINE'}</span></summary><div class="panel-body"><div class="map-viewport-toolbar"><span>Drag to pan · mouse wheel or buttons to zoom</span><div><button class="btn ghost compact-btn" data-map-zoom="out" aria-label="Zoom out">−</button><b data-map-zoom-label>${Math.round(viewport.scale*100)}%</b><button class="btn ghost compact-btn" data-map-zoom="in" aria-label="Zoom in">＋</button><button class="btn ghost compact-btn" data-map-zoom="reset">Reset</button></div></div><div class="server-player-map ${mapBg ? 'has-background' : ''}" data-live-map-world="${escapeHtml(world.id)}" ${mapBg ? `style="background-image:url('${mapBg}')"` : ''}>${overlayMarkers}${playersOnMap.map((pl) => `<button class="player-map-marker ${state.selectedPlayerId === String(pl.id || '') ? 'selected' : ''}" data-map-x="${Number(pl.map_point.x)}" data-map-y="${Number(pl.map_point.y)}" style="left:${Number(pl.map_point.x)*100}%;top:${Number(pl.map_point.y)*100}%;--yaw:${Number(pl.yaw || 0)}deg" title="${escapeHtml(pl.name || 'Player')}" data-map-player="${escapeHtml(pl.id || pl.name)}"><span class="facing">➤</span><b>${escapeHtml(pl.name || 'Player')}</b></button>`).join('')}${mapBg ? '' : '<div class="map-placeholder"><strong>Ashenfall map background not configured</strong><span>Tracking coordinates remain available. Refresh the map cache and the same map component is reused online.</span></div>'}</div><div class="map-attribution">${escapeHtml(state.mapCacheStatus?.attribution||'Ashenfall map imagery © Jagex Ltd. · RuneScape: Dragonwilds')}</div>${overlaysAligned?overlayFilters:'<div class="warning-box compact"><strong>Map calibration unavailable</strong><br/>Player and resource markers are hidden instead of being plotted against an unrelated image grid. Refresh the RSDW world-grid map or save verified manual bounds.</div>'}<div class="map-data-catalog"><div><strong>Mapped game data</strong><small>Filter controls and indexed records are kept below the map.</small></div>${categoryDetails}</div>${visibleOverlayPoints.length>=600?'<p class="muted-small map-density-note">Dense overlays are display-sampled to keep the live map responsive. The full RSDW index remains cached.</p>':''}${!tracker.tracker_connected ? `<div class="identity-box"><strong>${bridgeAvailable ? 'Waiting for RSDWTools roster' : 'Tracking bridge waiting for the game'}</strong><p>${bridgeAvailable ? 'The verified RSDWTools shared-memory bridge is running, but it has not returned a live player roster yet.' : 'Dragonwilds Sync installs the baseline RSDWTools functional bridge with debug output disabled. Live positions begin when the game or dedicated server starts producing telemetry; log-derived player presence remains available meanwhile.'}</p></div>` : ''}</div></details>`;
    if (!includeSetup) return mapPanel;
    const setup = `<details class="panel collapsible-panel" open><summary class="panel-header"><h2>Map Setup</h2><span class="panel-subtitle">World coordinates → normalized map coordinates</span></summary><div class="panel-body"><div class="header-actions map-source-actions" style="justify-content:flex-start"><button class="btn primary" id="refresh-latest-rsdw-map">Refresh Ashenfall Map</button><button class="btn ghost" id="choose-player-map-image">Choose Map Image</button><span class="muted-small">${state.mapCacheStatus?.version?`${escapeHtml(state.mapCacheStatus.source_title||'Ashenfall')} · ${escapeHtml(state.mapCacheStatus.version)} · ${state.mapCacheStatus.tile_count||0} tile(s)`:'Ashenfall map cache not checked yet'}</span></div><div class="health-evidence-grid map-calibration"><label><small>World Min X</small><input class="field" id="map-min-x" type="number" value="${escapeHtml(cal.world_min_x ?? '')}" /></label><label><small>World Max X</small><input class="field" id="map-max-x" type="number" value="${escapeHtml(cal.world_max_x ?? '')}" /></label><label><small>World Min Y</small><input class="field" id="map-min-y" type="number" value="${escapeHtml(cal.world_min_y ?? '')}" /></label><label><small>World Max Y</small><input class="field" id="map-max-y" type="number" value="${escapeHtml(cal.world_max_y ?? '')}" /></label></div><label class="checkbox-row"><input type="checkbox" id="map-invert-y" ${cal.invert_y === false ? '' : 'checked'} /> Invert map Y axis</label><label class="checkbox-row"><input type="checkbox" id="map-allow-remote" ${mapCfg.allow_remote_clients ? 'checked' : ''} /> Allow authenticated remote launcher clients to receive map availability</label><button class="btn primary" id="save-player-map-settings">Save Map Setup</button><div class="identity-box"><strong>One mapping pipeline</strong><p>RSDW telemetry emits Unreal coordinates; Dragonwilds Sync applies one map transform shared by Server → Map and RSDW Toolkit. There is no duplicate tracker/map implementation.</p></div></div></details>`;
    return `<div class="panel-grid map-layout">${mapPanel}${setup}</div>`;
  }

  function renderRsdwLiveMap() {
    const available = [singleplayerWorld(), ...serverWorlds()].filter(Boolean);
    const world = rsdwMapWorld();
    const single = singleplayerWorld();
    const privateBroadcast = !!single?.status?.broadcasting;
    const options = available.map((entry)=>`<option value="${escapeHtml(entry.id)}" ${world?.id===entry.id?'selected':''}>${escapeHtml(entry.name || 'World')}</option>`).join('');
    return `<div class="content rsdw-toolkit-page"><div class="page-header"><div><div class="eyebrow">Profile</div><h1>Live Map & Tracking</h1><div class="page-subtitle">One RSDW-backed telemetry surface reused by hosted Worlds and server management.</div></div><div class="header-actions"><span class="status-pill ${privateBroadcast?'online':'unknown'}">PRIVATE WORLD ${privateBroadcast?'BROADCASTING':'IDLE'}</span><button class="btn ghost" id="rsdw-map-refresh" ${world?'':'disabled'}>Refresh Tracking</button></div></div>${rsdwToolkitTabs()}<section class="rsdw-map-toolbar"><label><span>World</span><select class="select" id="rsdw-map-world" ${available.length?'':'disabled'}>${options || '<option>No Worlds configured</option>'}</select></label><div><strong>Baseline RSDWTools telemetry</strong><span>Dragonwilds Sync maintains the hidden RSDWTools functional bridge with debug output disabled. Live position markers appear when the selected game or server profile is running and emitting its roster.</span></div></section><div style="margin-top:16px">${playerMapPanelMarkup(world,{includeSetup:false,toolkit:true})}</div><div class="rsdw-credit">RSDW-powered tracking and tooling by <strong>Hi im Tat</strong> and the <strong>RSDW Modding Community</strong>. Dragonwilds Sync consumes the documented DevKit bridge.</div></div>`;
  }

  function characterLastLocationMarkup(character, payload=null) {
    const loc=payload?.last_location || character?.last_location;
    if(!loc || loc.x==null || loc.y==null) return `<div class="rsdw-last-location"><div><span>Last saved location</span><strong>Not surfaced by this save</strong></div></div>`;
    const worldId=(character?.selected_for_worlds||[])[0] || (character?.world_ids||[])[0] || state.data?.client?.active_private_world_id || 'singleplayer';
    const cfg=state.serverMapConfig[worldId] || privateWorldById(worldId)?.player_map || serverWorlds().find(w=>String(w.id)===String(worldId))?.player_map || {};
    const cal=cfg.calibration||{}; let point=null;
    const minX=Number(cal.world_min_x),maxX=Number(cal.world_max_x),minY=Number(cal.world_min_y),maxY=Number(cal.world_max_y);
    if([minX,maxX,minY,maxY].every(Number.isFinite) && maxX!==minX && maxY!==minY){
      let x=(Number(loc.x)-minX)/(maxX-minX), y=(Number(loc.y)-minY)/(maxY-minY); if(cal.invert_y!==false)y=1-y;
      if(x>=0&&x<=1&&y>=0&&y<=1)point={x,y};
    }
    const bg=cfg.background_data || state.mapCacheStatus?.data_url || '';
    return `<div class="rsdw-last-location"><div class="rsdw-last-location-copy"><span>Last saved location</span><strong>X ${Math.round(Number(loc.x))} · Y ${Math.round(Number(loc.y))} · Z ${Math.round(Number(loc.z||0))}</strong><small>${escapeHtml(loc.confidence==='high'?'Save-backed position':'Best-effort save position')}${worldId?` · ${escapeHtml(rsdwWorldName(worldId))}`:''}</small></div>${bg&&point?`<div class="rsdw-location-mini-map" style="background-image:url('${bg}')"><i style="left:${point.x*100}%;top:${point.y*100}%"></i></div>`:''}</div>`;
  }

  function renderRsdwToolkit() {
    if (state.rsdwSection === 'live-map') return renderRsdwLiveMap();
    const chars = state.characters || [];
    const selected = chars.find((character)=>character.id===state.characterSelectedId) || chars[0] || null;
    const payload = selected?.id === state.characterSelectedId ? state.rsdwCharacterPayload : null;
    const profile = selected?.profile || {};
    const tool = translatedRsdwTool(RSDW_TOOLS.find((entry)=>entry.id===state.rsdwTool) || RSDW_TOOLS[0]);
    const sourceLocal = state.rsdwSource?.mode === 'local';
    const selector = chars.length ? `<div class="character-selector-strip rsdw-selector">${chars.map((character)=>{
      const meta=character.profile||{}; const portrait=meta.portrait_data; const active=selected?.id===character.id;
      return `<button class="character-mini ${active?'active':''}" data-rsdw-character="${escapeHtml(character.id)}">${portrait?`<img src="${portrait}" alt=""/>`:`<span class="character-mini-avatar">${escapeHtml(initials(meta.label||character.player_name||character.file_name))}</span>`}<span><strong>${escapeHtml(meta.label||character.player_name||character.file_name)}</strong><small>${character.editable?'RSDW editable':'Preserve only'} · ${new Date((character.modified_at||0)*1000).toLocaleDateString()}</small></span></button>`;
    }).join('')}</div>` : '';
    if (state.rsdwToolkitLoading && !chars.length) return `<div class="content"><div class="page-header"><div><div class="eyebrow">Profile</div><h1>Characters</h1><div class="page-subtitle">Loading character tools and saves…</div></div></div><div class="empty-state"><div class="spinner"></div><strong>Preparing Character Tools</strong></div></div>`;
    if (!selected) return `<div class="content"><div class="page-header"><div><div class="eyebrow">Profile</div><h1>Characters</h1><div class="page-subtitle">RSDW-powered identity, progression, inventory, and save tooling integrated into your Profile.</div></div><div class="header-actions"><button class="btn ghost" id="rsdw-refresh-toolkit">Refresh RSDW Toolkit</button></div></div>${rsdwToolkitTabs()}<div class="empty-state"><strong>No Dragonwilds characters found.</strong><span>Link your Dragonwilds installation in Settings → Client to use Character & Saves, or open Live Map & Tracking for hosted Worlds.</span></div><div class="rsdw-credit">RSDW tooling by <strong>Hi im Tat</strong> and the <strong>RSDW Modding Community</strong>.</div></div>`;
    const characterTabs=characterProfileTabs(selected);
    const charName = profile.label || selected.player_name || selected.file_name || 'Character';
    const linked = (selected.world_ids || []).map((id)=>`<span class="world-link-chip">${escapeHtml(rsdwWorldName(id))}${(selected.selected_for_worlds||[]).includes(id)?' · Preferred':''}</span>`).join('') || '<span class="muted-small">No World associations yet.</span>';
    const statNative=(state.rsdwNativeDraft?.characterId===selected.id&&state.rsdwNativeDraft?.native_editor)||payload?.native_editor||{};
    const trainedSkills=(statNative.skills||[]).filter((row)=>Number(row.xp||0)>0);
    const stats = [
      ['Trained skills', trainedSkills.length],
      ['Total skill XP', trainedSkills.reduce((sum,row)=>sum+Number(row.xp||0),0).toLocaleString()],
      ['Inventory slots', (selected.inventory||[]).length],
      ['Equipped', (selected.equipment||[]).length],
      [t('worlds'), (selected.world_ids||[]).length],
    ];
    const archetype = CHARACTER_ARCHETYPES[profile.archetype] ? profile.archetype : 'mage';
    const subtype = CHARACTER_ARCHETYPES[archetype].some(([id])=>id===profile.subtype) ? profile.subtype : CHARACTER_ARCHETYPES[archetype][0][0];
    const archetypeEditor = `<div class="character-archetype-editor"><div><strong>${escapeHtml(et('combatIdentity'))}</strong><span>${escapeHtml(et('combatHelp'))}</span></div><div class="character-archetype-fields"><label><small>${escapeHtml(et('archetype'))}</small><select class="select" id="character-archetype">${Object.keys(CHARACTER_ARCHETYPES).map((id)=>`<option value="${id}" ${id===archetype?'selected':''}>${id[0].toUpperCase()+id.slice(1)}</option>`).join('')}</select></label><label><small>${escapeHtml(et('subtype'))}</small><select class="select" id="character-subtype">${CHARACTER_ARCHETYPES[archetype].map(([id,label])=>`<option value="${id}" ${id===subtype?'selected':''}>${label}</option>`).join('')}</select></label><button class="btn ghost" id="save-character-archetype">${escapeHtml(et('saveTags'))}</button><button class="btn primary" id="apply-character-archetype" ${selected.editable?'':'disabled'}>${escapeHtml(et('previewInject'))}</button></div>${profile.archetype?`<div class="character-archetype-tags"><span>${escapeHtml(profile.archetype.toUpperCase())}</span><span>${escapeHtml(String(profile.subtype||'').replace(/-/g,' ').toUpperCase())}</span>${profile.template_applied_at?'<small>Loadout applied</small>':''}</div>`:''}</div>`;
    const toolNav = `<div class="rsdw-tool-nav">${RSDW_TOOLS.map((rawEntry)=>{const entry=translatedRsdwTool(rawEntry);return `<button class="rsdw-tool-tile ${tool.id===entry.id?'active':''}" data-rsdw-tool="${entry.id}" ${selected.editable?'':'disabled'}><img src="${entry.icon}" alt=""/><span><strong>${escapeHtml(entry.label)}</strong><small>${escapeHtml(entry.subtitle)}</small></span></button>`;}).join('')}</div>`;
    const sourceBadge = sourceLocal ? `<span class="status-pill online">LOCAL · ${escapeHtml((state.rsdwSource.revision||'').slice(0,8) || 'CACHED')}</span>` : '<span class="status-pill unknown">OFFICIAL WEB FALLBACK</span>';
    const rawEditSurface = rsdwEditorSurfaceMarkup(selected,payload,tool);
    const editSurface = rawEditSurface;
    const itemEditor=state.rsdwNativeTools['item-editor']||{};
    const repositorySlot=String(state.rsdwEquipmentRepositorySlot||'');
    const repositoryItems=repositorySlot?Object.values(itemEditor.tabs||{}).flatMap((tab)=>tab.items||[]).filter((row)=>characterEquipmentCompatible(row,repositorySlot)&&(!state.rsdwEquipmentSearch||`${row.name||''} ${row.category||''} ${row.description||''}`.toLowerCase().includes(state.rsdwEquipmentSearch.toLowerCase()))).slice(0,80):[];
    const repositoryMarkup=repositorySlot?`<div class="studio-repository-backdrop" id="studio-repository-backdrop"><section class="studio-equipment-repository" role="dialog" aria-label="${escapeHtml(repositorySlot)} equipment repository"><div class="panel-header"><div><div class="eyebrow">Shared Item Editor Repository</div><h2>${escapeHtml(repositorySlot)} Equipment</h2><span class="panel-subtitle">${repositorySlot==='Main Hand'||repositorySlot==='Off Hand'?'Choose a compatible item; the closest available RSDWModel asset is used in the live preview.':'Preview-only until Apply to Character.'} ${repositoryItems.length} compatible current-catalog items shown.</span></div><button class="btn ghost" id="close-studio-repository">×</button></div><div class="studio-repository-search"><input class="field" id="studio-equipment-search" value="${escapeHtml(state.rsdwEquipmentSearch)}" placeholder="Search compatible equipment…"/><button class="btn ghost" id="studio-equipment-search-apply">Search</button></div><div class="studio-repository-grid">${repositoryItems.map((row)=>`<button class="studio-repository-item" draggable="true" data-studio-equipment-item="${escapeHtml(row.item_data)}" data-studio-equipment-name="${escapeHtml(row.name||'')}" data-studio-equipment-type="${escapeHtml(row.equipment)}"><img src="${escapeHtml(rsdwAssetUrl(row.icon))}" alt="" loading="lazy"/><span><strong>${escapeHtml(row.name)}</strong><small>${escapeHtml(row.category||row.equipment)}</small></span></button>`).join('')||'<div class="empty-state compact">No compatible catalog items match this search.</div>'}</div></section></div>`:'';
    const equipmentStudioMarkup=tool.id==='character-editor'?repositoryMarkup:'';
    return `<div class="content rsdw-toolkit-page studio-combined-page">
      <div class="page-header"><div><div class="eyebrow">${escapeHtml(t('profile'))}</div><h1>${escapeHtml(t('characters'))}</h1><div class="page-subtitle">${escapeHtml(et('charactersPageSubtitle'))}</div></div><div class="header-actions"><button class="btn ghost" id="detach-profile">${detachedMode?'↙ Return to Application':`↗ ${escapeHtml(et('openInWindow'))}`}</button>${sourceBadge}<button class="btn ghost" id="rsdw-refresh-toolkit">${escapeHtml(sourceLocal?et('refreshUpstream'):et('hydrateLocal'))}</button><button class="btn ghost" id="rsdw-import-character">${escapeHtml(et('importProfile'))}</button><button class="btn primary" id="rsdw-export-character">${escapeHtml(et('exportCharacter'))}</button></div></div>
      ${rsdwToolkitTabs()}
      ${selector}
      ${characterTabs}
      <div class="rsdw-character-details studio-character-summary studio-combined-summary"><section class="studio-summary-card studio-overview-card"><div class="rsdw-character-identity">${profile.portrait_data?`<img src="${profile.portrait_data}" alt=""/>`:`<div class="character-profile-avatar">${escapeHtml(initials(charName))}</div>`}<div><div class="eyebrow">${escapeHtml(et('selectedCharacter'))}</div><h2>${escapeHtml(charName)}</h2><strong>${escapeHtml(selected.guid || 'No GUID surfaced')}</strong><span>${escapeHtml(selected.file_name || '')}</span></div><span class="status-pill ${selected.editable?'online':'unknown'}">${selected.editable?'RSDW READY':'PRESERVE ONLY'}</span></div><div class="rsdw-metric-grid">${stats.map(([label,value])=>`<div><span>${label}</span><strong>${escapeHtml(String(value))}</strong></div>`).join('')}</div><div class="rsdw-character-meta"><div><span>${escapeHtml(et('lastModified'))}</span><strong>${new Date((selected.modified_at||0)*1000).toLocaleString()}</strong></div><div><span>${escapeHtml(et('saveSize'))}</span><strong>${(Number(selected.size||0)/1024).toFixed(1)} KiB</strong></div><div><span>SHA-256</span><code>${escapeHtml(String(selected.sha256||'').slice(0,16))}…</code></div><div><span>${escapeHtml(et('profileStatus'))}</span><strong>${profile.favorite?`★ ${escapeHtml(et('favorite'))}`:'Standard'}</strong></div></div><div class="rsdw-character-actions"><button class="btn ghost" id="rsdw-change-portrait">${escapeHtml(et('chooseImage'))}</button><button class="btn ghost" id="rsdw-toggle-favorite">${escapeHtml(profile.favorite?et('removeFavorite'):et('favorite'))}</button><button class="btn ghost" id="rsdw-clone-character">${escapeHtml(et('cloneCharacter'))}</button><button class="btn ghost" id="rsdw-backup-export">Export .rsdwl</button><button class="btn danger" id="rsdw-delete-character">${escapeHtml(et('deleteCharacter'))}</button></div></section><section class="studio-summary-card studio-world-card"><div class="rsdw-world-associations"><strong>${escapeHtml(et('worldAssociations'))}</strong><div>${linked}</div></div></section>${state.rsdwHydrationError?`<div class="warning-box compact">${escapeHtml(state.rsdwHydrationError)}</div>`:''}</div>
      <section class="studio-summary-card studio-combat-card">${archetypeEditor}</section>
      <div class="rsdw-tool-launch-hint">Identity, the dedicated 3D renderer, Appearance, progression, and inventory share one cached character-creator workspace.</div>${toolNav}
      ${equipmentStudioMarkup}
      ${editSurface}
      <div class="rsdw-credit">RSDW-powered tooling by <strong>Hi im Tat</strong> and the <strong>RSDW Modding Community</strong>. Dragonwilds Sync handles profile selection, backups, synchronization, and safe writeback.</div>
    </div>`;
  }

  function statusPill(world) {
    if (world.status?.blocked) {
      const kind = world.status.blocked_kind || 'ip';
      const label = kind === 'profile' ? 'Your Sync Profile' : kind === 'country' ? 'Your country' : kind === 'region' ? 'Your region' : 'Your IP';
      return `<span class="status-pill blocked" title="${escapeHtml(`${label} is blocked by this World's host: ${world.status.blocked_reason || ''}`)}">🚫 BLOCKED</span>`;
    }
    const online = world.status?.online;
    if (online === true) return `<span class="status-pill online">● ONLINE</span>`;
    if (online === false) return `<span class="status-pill offline">● OFFLINE</span>`;
    return `<span class="status-pill unknown">● UNKNOWN</span>`;
  }

  function worldSyncIdentity(world) {
    const shared = world?.shared || {};
    const remote = world?.status?.world_sync || world?.manifest_cache?.world_sync || {};
    const fingerprint = String(shared.fingerprint || remote.fingerprint || world?.manifest_cache?.launcher_fingerprint || '');
    const claimed = String(shared.fingerprint_claimed || '');
    const verified = !!shared.fingerprint_verified && /^dws1-[0-9a-f]{24}$/i.test(fingerprint);
    return { fingerprint, claimed, verified };
  }

  function updateOperationProgress(job) {
    if(!state.operation)return;Object.assign(state.operation,{phase:job.phase||state.operation.phase,percent:Number(job.percent||0),detail:job.message||state.operation.detail,changed_files:job.changed_files,unchanged_files:job.unchanged_files,downloaded_bytes:job.downloaded_bytes});
    const banner=root.querySelector('.operation-banner');if(!banner)return;
    const detail=banner.querySelector('[data-operation-detail]');if(detail)detail.textContent=state.operation.detail||'';
    const bar=banner.querySelector('[data-operation-progress]');if(bar)bar.style.width=`${Math.max(0,Math.min(100,state.operation.percent||0))}%`;
    const percent=banner.querySelector('[data-operation-percent]');if(percent)percent.textContent=`${Math.round(state.operation.percent||0)}%`;
    const phases=['connecting','comparing','downloading','unpacking','applying','verifying','profile','ready'],active=Math.max(0,phases.indexOf(state.operation.phase||'connecting'));
    banner.querySelectorAll('[data-operation-phase]').forEach((node,index)=>{node.classList.toggle('complete',index<active);node.classList.toggle('active',index===active);});
    const counts=banner.querySelector('[data-operation-counts]');if(counts&&Number.isFinite(Number(job.changed_files)))counts.innerHTML=`<span>${Number(job.changed_files||0)} changed</span><span>${Number(job.unchanged_files||0)} unchanged</span>${job.downloaded_bytes?`<span>${formatBytes(job.downloaded_bytes)} transferred</span>`:''}`;
  }

  async function runWorldSyncJob(world, action='play', forceComplete=false) {
    if(state.operation)throw new Error(`${state.operation.title} is already in progress.`);
    const diagnostics=state.data?.application?.connection_diagnostic_reports===true;
    state.operation={title:action==='play'?'Synchronizing & launching World':'Synchronizing World',detail:'Connecting to the World host…',phase:'connecting',percent:0,diagnostics,position:{x:0,y:0}};render();
    try{
      const started=await api.invoke('world.sync.job.start',{id:world.id,action,diagnostics,force_complete:!!forceComplete});const jobId=started.job_id;if(!jobId)throw new Error('World Sync did not return a job identifier.');
      while(true){await new Promise(resolve=>setTimeout(resolve,250));const job=await api.invoke('world.sync.job.status',{job_id:jobId});updateOperationProgress(job);if(job.status==='failed'){if(job.diagnostic_path)toast('Connection report saved',job.diagnostic_path,'warning');throw new Error(job.error||job.message||'World Sync failed.');}if(job.status==='complete'){if(job.diagnostic_path)toast('Connection report saved',job.diagnostic_path,'success');return job.response;}}
    }finally{state.operation=null;render();}
  }

  function worldSaveDownloadPolicy(world) {
    const candidates=[world?.status?.world_save_download,world?.manifest_cache?.world_save_download,world?.shared?.world_save_download];
    const source=candidates.find((value)=>value&&typeof value.enabled==='boolean')||{};
    const known=typeof source.enabled==='boolean';
    return {known,enabled:known?source.enabled:true,allowed:source.allowed!==false,
      disabled:known&&source.enabled===false,remainingSeconds:Number(source.remaining_seconds||0)};
  }

  function syncBadgeMarkup(world) {
    const sync = worldSyncIdentity(world);
    if (!sync.verified) return '';
    const operator=world?.shared?.operator_verified?`<span class="studio-compat operator-verified" title="Ed25519 operator identity: ${escapeHtml(world.shared.operator_fingerprint||'')}">OPERATOR ✓</span>`:'';
    return `<span class="studio-compat sync-verified" title="Verified Dragonwilds Sync fingerprint: ${escapeHtml(sync.fingerprint)}">SYNC ✓ <code>${escapeHtml(sync.fingerprint.slice(-6))}</code></span>${operator}`;
  }

  function worldCountryMarkup(world, compact = false) {
    const code = String(world?.status?.country_code || world?.public_discovery?.country_code || '').toUpperCase();
    const name = String(world?.status?.country_name || world?.public_discovery?.country_name || (code ? countryName(code) : ''));
    if (!code && !name) return '';
    return `<span class="world-country" title="Server IP geolocation">${code ? flagMarkup(code) : ''}${compact ? '' : `<b>${escapeHtml(name || code)}</b>`}</span>`;
  }

  function worldHostingMarkup(world, compact = false) {
    const status=world?.status||{};
    const provider=String(status.hosting_provider||world?.public_discovery?.hosting_provider||'').trim();
    if(!provider)return '';
    const org=String(status.hosting_org||'').trim();
    const initials=provider.split(/\s+/).map((part)=>part[0]||'').join('').slice(0,3).toUpperCase();
    return `<span class="world-hosting" title="Hosted infrastructure${org?`: ${escapeHtml(org)}`:''}"><i aria-hidden="true">☁</i>${compact?'':`<b>${escapeHtml(provider)}</b>`}<small>${escapeHtml(initials)}</small></span>`;
  }

  function badgeMarkup(badge) {
    const key = String(badge || '').toLowerCase();
    const cls = key.includes('rune') ? 'runeschema' : key.includes('ue4') ? 'ue4ss' : key.includes('pak') ? 'paks' : 'vanilla';
    return `<span class="badge ${cls}">${escapeHtml(String(badge).toUpperCase())}</span>`;
  }

  function advertisedModFamily(value) {
    const text=typeof value==='string'?value:[value?.section,value?.group,value?.kind,value?.type,value?.loader,value?.classification,value?.path,value?.name].filter(B