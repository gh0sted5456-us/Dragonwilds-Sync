import base from './worker.js';

// Phase 5 is deliberately a narrow wrapper around the proven signed V3 worker.
// The base worker remains the credential/HMAC/rate-limit authority. Only after a
// heartbeat has been accepted do we retain its public-safe Remote Admin handoff.
const REMOTE_ACTIVE_SECONDS = 15 * 60;

const now = () => Math.floor(Date.now() / 1000);

async function ensureRemoteTable(env) {
  await env.DB.prepare(`CREATE TABLE IF NOT EXISTS world_remote_admin_v1 (
    world_id TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    updated_at INTEGER NOT NULL
  )`).run();
}

async function ensurePublicMetaTable(env) {
  await env.DB.prepare(`CREATE TABLE IF NOT EXISTS world_public_meta_v1 (
    world_id TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    updated_at INTEGER NOT NULL
  )`).run();
}

function sanitizePublicMeta(heartbeat) {
  const declared = heartbeat?.platform_compatibility && typeof heartbeat.platform_compatibility === 'object' ? heartbeat.platform_compatibility : {};
  const ratings = heartbeat?.platform_ratings && typeof heartbeat.platform_ratings === 'object' ? heartbeat.platform_ratings : {};
  const platform_compatibility = {};
  const platform_ratings = {};
  for (const key of ['pc','steam','epic','playstation','nintendo','switch2','xbox']) {
    if (declared[key] != null) platform_compatibility[key] = Boolean(declared[key]);
    const row=ratings[key];const count=Math.max(0,Math.min(100000,Number(row?.count||0)));const average=Math.max(0,Math.min(5,Number(row?.average||0)));
    if (count) platform_ratings[key]={average:Math.round(average*100)/100,count};
  }
  return { platform_compatibility, platform_ratings };
}

async function retainPublicMeta(env, heartbeat) {
  await ensurePublicMetaTable(env);
  const worldId=String(heartbeat?.world_id||'');if(!worldId)return;
  await env.DB.prepare(`INSERT INTO world_public_meta_v1 (world_id,payload_json,updated_at)
    VALUES (?1,?2,?3)
    ON CONFLICT(world_id) DO UPDATE SET payload_json=excluded.payload_json,updated_at=excluded.updated_at`)
    .bind(worldId,JSON.stringify(sanitizePublicMeta(heartbeat)),now()).run();
}

function safeHttpsBase(value) {
  try {
    const url = new URL(String(value || '').trim());
    if (url.protocol !== 'https:' || !url.hostname || url.username || url.password || url.hash) return '';
    url.search = '';
    url.pathname = url.pathname.replace(/\/$/, '');
    return url.toString().replace(/\/$/, '');
  } catch (_) {
    return '';
  }
}

function sanitizeRemote(input, heartbeat) {
  const row = input && typeof input === 'object' && !Array.isArray(input) ? input : {};
  const endpoint = safeHttpsBase(row.endpoint);
  if (!row.configured || !row.enabled || !row.available || !endpoint) return null;
  const worldId = String(heartbeat?.world_id || '').slice(0, 120);
  if (!worldId) return null;
  return {
    configured: true,
    enabled: true,
    available: true,
    browser_compatible: true,
    endpoint,
    ping_path: '/api/v1/remote-admin/ping',
    login_path: '/admin/login',
    authority: 'target-world',
    world_id: worldId,
    world_name: String(heartbeat?.name || row.world_name || '').slice(0, 160),
    fingerprint: String(row.fingerprint || '').slice(0, 96),
    auth: Array.isArray(row.auth) ? row.auth.filter((v) => ['remote_user', 'server_admin_password'].includes(String(v))).slice(0, 2) : [],
  };
}

async function retainRemote(env, heartbeat) {
  await ensureRemoteTable(env);
  const worldId = String(heartbeat?.world_id || '');
  if (!worldId) return;
  const remote = sanitizeRemote(heartbeat?.remote_management, heartbeat);
  if (!remote) {
    await env.DB.prepare('DELETE FROM world_remote_admin_v1 WHERE world_id=?1').bind(worldId).run();
    return;
  }
  await env.DB.prepare(`INSERT INTO world_remote_admin_v1 (world_id,payload_json,updated_at)
    VALUES (?1,?2,?3)
    ON CONFLICT(world_id) DO UPDATE SET payload_json=excluded.payload_json,updated_at=excluded.updated_at`)
    .bind(worldId, JSON.stringify(remote), now()).run();
}

async function remoteRows(env, ids) {
  await ensureRemoteTable(env);
  const wanted = [...new Set((ids || []).map(String).filter(Boolean))].slice(0, 500);
  if (!wanted.length) return new Map();
  // D1 supports bound parameters but the number of rows is bounded by the base
  // world's 500-result contract. Chunk to avoid SQLite variable limits.
  const map = new Map();
  for (let offset = 0; offset < wanted.length; offset += 100) {
    const chunk = wanted.slice(offset, offset + 100);
    const marks = chunk.map((_, index) => `?${index + 1}`).join(',');
    const result = await env.DB.prepare(`SELECT world_id,payload_json,updated_at FROM world_remote_admin_v1 WHERE world_id IN (${marks})`).bind(...chunk).all();
    for (const row of result.results || []) {
      if (Number(row.updated_at || 0) < now() - REMOTE_ACTIVE_SECONDS) continue;
      try {
        const parsed = JSON.parse(row.payload_json || '{}');
        if (parsed?.endpoint && parsed?.authority === 'target-world') map.set(String(row.world_id), parsed);
      } catch (_) {}
    }
  }
  return map;
}

async function publicMetaRows(env, ids) {
  await ensurePublicMetaTable(env);const wanted=[...new Set((ids||[]).map(String).filter(Boolean))].slice(0,500);const map=new Map();
  for(let offset=0;offset<wanted.length;offset+=100){const chunk=wanted.slice(offset,offset+100);const marks=chunk.map((_,index)=>`?${index+1}`).join(',');const result=await env.DB.prepare(`SELECT world_id,payload_json,updated_at FROM world_public_meta_v1 WHERE world_id IN (${marks})`).bind(...chunk).all();for(const row of result.results||[]){if(Number(row.updated_at||0)<now()-REMOTE_ACTIVE_SECONDS)continue;try{map.set(String(row.world_id),JSON.parse(row.payload_json||'{}'));}catch(_){}}}
  return map;
}

async function augmentWorldPayload(env, payload) {
  if (!payload || typeof payload !== 'object') return payload;
  const worlds = Array.isArray(payload.worlds) ? payload.worlds : null;
  if (worlds) {
    const remotes = await remoteRows(env, worlds.map((world) => world?.world_id));
    const metadata = await publicMetaRows(env, worlds.map((world) => world?.world_id));
    payload.worlds = worlds.map((world) => {
      const remote = remotes.get(String(world?.world_id || ''));
      const meta = metadata.get(String(world?.world_id || '')) || {};
      return { ...world, ...meta, ...(remote?{remote_management:remote}:{}), capabilities: { ...(world?.capabilities || {}), ...(remote?{remote_management:true}:{}) } };
    });
    payload.capabilities = { ...(payload.capabilities || {}), remote_admin_handoff: true };
    return payload;
  }
  if (payload.world_id) {
    const remotes = await remoteRows(env, [payload.world_id]);
    const metadata = await publicMetaRows(env, [payload.world_id]);
    Object.assign(payload,metadata.get(String(payload.world_id))||{});
    const remote = remotes.get(String(payload.world_id));
    if (remote) {
      payload.remote_management = remote;
      payload.capabilities = { ...(payload.capabilities || {}), remote_management: true };
    }
  }
  return payload;
}

function jsonResponse(payload, response) {
  const headers = new Headers(response.headers);
  headers.set('content-type', 'application/json; charset=utf-8');
  headers.set('cache-control', 'no-store');
  return new Response(JSON.stringify(payload), { status: response.status, statusText: response.statusText, headers });
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = url.pathname.replace(/\/$/, '') || '/';
    const heartbeatClone = request.method === 'POST' && path === '/api/v1/heartbeat' ? request.clone() : null;
    const response = await base.fetch(request, env, ctx);

    if (heartbeatClone && response.ok) {
      try {
        const heartbeat = await heartbeatClone.json();
        await Promise.all([retainRemote(env, heartbeat),retainPublicMeta(env, heartbeat)]);
      } catch (_) {
        // The base worker already accepted/rejected the authoritative heartbeat.
        // Remote handoff metadata is optional and never changes that result.
      }
      return response;
    }

    if (request.method === 'GET' && (path === '/api/v1/worlds' || path.startsWith('/api/v1/worlds/')) && response.ok) {
      try {
        const payload = await response.clone().json();
        return jsonResponse(await augmentWorldPayload(env, payload), response);
      } catch (_) { return response; }
    }

    if (request.method === 'GET' && (path === '/api/v1/capabilities' || path === '/.well-known/dragonwilds-sync') && response.ok) {
      try {
        const payload = await response.clone().json();
        payload.remote_admin_handoff = true;
        payload.remote_admin_handoff_protocol = 1;
        return jsonResponse(payload, response);
      } catch (_) { return response; }
    }

    return response;
  },
};
