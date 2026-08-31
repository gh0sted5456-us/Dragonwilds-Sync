const { contextBridge } = require('electron');

const fixture = {
  profile_id: 'effing-desync-fixture',
  mode: 'server',
  profile_kind: 'dedicated',
  profile_scope: 'Hosted Server',
  world_name: 'Effing Desync',
  description: 'A dedicated Dragonwilds World managed by Quick Launch.',
  mods: { count: 48, cached: true, path: '' },
  sync: { serving: false, port: 27051 },
  network: { public_directory_enabled: false, broadcast_destinations: [] },
  runtime: { runtime: { state: 'Running' } },
  telemetry: {
    metrics: { process_cpu_percent: 18.4, process_ram_bytes: 1644167168, ram_percent: 57.8, ram_used_bytes: 9921374454, ram_total_bytes: 17179869184, net_down_bps: 82432, net_up_bps: 31872 },
    history: Array.from({ length: 48 }, (_, index) => ({
      process_cpu_percent: 9 + ((index * 7) % 23), process_ram_bytes: 1500000000 + index * 2800000,
      ram_percent: 51 + ((index * 3) % 11), ram_used_bytes: 9000000000 + index * 17000000, ram_total_bytes: 17179869184,
      net_down_bps: 22000 + ((index * 19031) % 140000), net_up_bps: 9000 + ((index * 11017) % 76000)
    })),
    ping_ms: 42, ping_source: 'Observed client to RSDragonwilds'
  },
  active: true,
  cl: 'CL-232224',
  players: [],
  launch_sequence: [
    'Apply profile mods and settings',
    'Start dedicated game process',
    'Connect DragonLink game bridge',
    'Start multiplayer broadcast',
    'Start and maintain Sync broadcast'
  ],
  controls: { start: true, stop: true, restart: true, update_restart: true, console: true, broadcast_message: true }
};

contextBridge.exposeInMainWorld('dragonwildsV3', { quickContext: () => ({ enabled: true, profileId: fixture.profile_id, mode: 'server', autoStart: false }) });
contextBridge.exposeInMainWorld('dragonwilds', {
  invoke: async (method) => {
    if (method === 'quick.status') return fixture;
    if (method === 'quick.console.get') return { events: [
      { ts: Date.now() / 1000, source: 'server', message: 'Quick dashboard fixture ready.' },
      { ts: Date.now() / 1000, source: 'sync', message: 'Waiting for World startup.' }
    ] };
    return { ok: true };
  },
  openMainWindow: () => undefined,
  openPath: async () => undefined
});
