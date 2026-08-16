const previewState = {
  schema_version: 2,
  application: { server_mode_enabled: true, game_dir: 'D:\\SteamLibrary\\steamapps\\common\\RSDragonwilds\\RSDragonwilds', game_exe: '', keep_core_persistent: true, background_server_checks: true },
  player_profile: { display_name: 'Luke', about: 'Dragonwilds player and server operator.', avatar_data: '' },
  client: {
    active_world_id: 'valhalla', live_world_id: 'valhalla', client_id: 'preview01',
    worlds: [
      {
        id: 'valhalla', nickname: '', identity: { world_name: 'Valhalla Friends', server_profile_id_hint: 'abc123' },
        connection: { internal_ip: '192.168.1.50:7777', external_ip: '71.22.33.44:7777', preference: 'auto', last_successful_route: 'internal', last_successful_address: '192.168.1.50:7777' },
        credentials: { password: 'demo', server_key: 'demo', remember: true },
        presentation: { description: 'A heavily modded cooperative survival world for friends.', tags: ['co-op','survival','friends'], mod_badges: ['UE4SS','RUNESCHEMA','PAKS'], icon_b64: 'assets/valhalla-friends-icon.png', banner_b64: 'assets/valhalla-friends-banner.png' },
        status: { online: true, ping_ms: 18.6, player_count: 4, uptime_seconds: 12480, manifest_version: 42 },
        manifest_cache: { mod_summary: [
          {name:'DragonCore',section:'ue4ss',classification:'player_required',category:'permanent'},
          {name:'Extended Resources',section:'runeschema',classification:'player_required',category:'permanent'},
          {name:'Server Admin Tools',section:'ue4ss',classification:'server_only',category:'permanent'}
        ]}, last_sync: { timestamp:'2026-08-12 18:42', version:42 }
      },
      {
        id: 'hardcore', nickname: 'The Boys', identity: { world_name: 'Hardcore Expedition', server_profile_id_hint: '' },
        connection: { internal_ip: '192.168.1.50:7777', external_ip: '71.22.33.44:7777', preference: 'auto', last_successful_route: 'external', last_successful_address: '71.22.33.44:7777' },
        credentials: { password: '', server_key: '', remember: true },
        presentation: { description: 'A separate profile on the same physical server with harsher survival settings.', tags: ['hardcore','pve'], mod_badges: ['RUNESCHEMA'], icon_b64: '', banner_b64: '' },
        status: { online: false, ping_ms: null, player_count: null, uptime_seconds: null, manifest_version: 18 }, manifest_cache: null, last_sync: null
      }
    ]
  },
  server: { active_world_id: 'host1' },
  server_profiles: [{ id:'host1', name:'Valhalla Friends', description:'A heavily modded cooperative survival world for friends.', tags:['co-op','survival'], icon_b64:'assets/valhalla-friends-icon.png', banner_b64:'assets/valhalla-friends-banner.png', auto_ue4ss:true, auto_runeschema:true, rating_average:4.8, rating_count:22 }]
};
window.dragonwilds = {
  invoke: async (method, params) => method === 'bootstrap' ? structuredClone(previewState) : structuredClone(previewState),
  pickImage: async () => null,
  pickDirectory: async () => null,
  pickExecutable: async () => null,
  openPath: async () => true,
};
