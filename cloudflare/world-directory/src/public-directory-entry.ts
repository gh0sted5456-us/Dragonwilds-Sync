import coreWorker from './index';
import { publicScanStatus, scanPublicSourcesIncrementally } from './rotating-public-scan';

const core = coreWorker as any;
const DEFAULT_SYNC_FORGET_SECONDS = 6 * 60 * 60;
const DEFAULT_OFFLINE_AFTER_SECONDS = 30 * 60;
const DIRECTORY_PAGE_SIZE = 10;

function corsHeaders(): HeadersInit {
  return {
    'access-control-allow-origin': '*',
    'access-control-allow-methods': 'GET, OPTIONS',
    'access-control-allow-headers': 'content-type',
  };
}

function clampInt(value: unknown, fallback: number, min: number, max: number): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.min(max, Math.max(min, Math.trunc(parsed)));
}

function syncForgetSeconds(env: any): number {
  return clampInt(env?.SYNC_FORGET_AFTER_SECONDS, DEFAULT_SYNC_FORGET_SECONDS, 1800, 86400);
}

function offlineAfterSeconds(env: any): number {
  return clampInt(env?.OFFLINE_AFTER_SECONDS, DEFAULT_OFFLINE_AFTER_SECONDS, 60, 86400);
}

function isOnlineStatus(value: unknown): boolean {
  const status = String(value || '').trim().toLowerCase();
  return status === 'online' || status === 'starting' || status === 'maintenance';
}

function isSyncWorld(world: Record<string, any>): boolean {
  return Boolean(world?.is_sync_world || world?.directory_source === 'dragonwilds-sync');
}

function seenSeconds(world: Record<string, any>): number {
  const raw = Number(world?.last_seen || 0);
  if (!Number.isFinite(raw) || raw <= 0) return 0;
  return raw > 1e12 ? Math.floor(raw / 1000) : Math.floor(raw);
}

function syncWorldAge(world: Record<string, any>, now: number): number {
  const seen = seenSeconds(world);
  return seen > 0 ? Math.max(0, now - seen) : Number.MAX_SAFE_INTEGER;
}

function decorateWorld(world: Record<string, any>, now: number): Record<string, any> {
  if (!isSyncWorld(world)) {
    return { ...world, directory_category: 'public' };
  }
  const online = isOnlineStatus(world.status);
  return {
    ...world,
    directory_category: online ? 'sync-online' : 'sync-offline',
    sync_offline_age_seconds: online ? 0 : syncWorldAge(world, now),
  };
}

function compareDirectoryWorlds(a: Record<string, any>, b: Record<string, any>): number {
  const aSync = isSyncWorld(a);
  const bSync = isSyncWorld(b);
  if (aSync !== bSync) return Number(bSync) - Number(aSync);

  const aOnline = isOnlineStatus(a.status);
  const bOnline = isOnlineStatus(b.status);
  if (aOnline !== bOnline) return Number(bOnline) - Number(aOnline);

  const seenDiff = seenSeconds(b) - seenSeconds(a);
  if (seenDiff) return seenDiff;

  const aPlayers = Number(a?.players?.current || 0);
  const bPlayers = Number(b?.players?.current || 0);
  if (aPlayers !== bPlayers) return bPlayers - aPlayers;

  return String(a?.world_name || '').localeCompare(String(b?.world_name || ''));
}

async function totalSyncWorldStarts(env: any): Promise<number> {
  try {
    const row = await env.DB.prepare(
      "SELECT counter_value FROM network_counters WHERE counter_key = 'total_sync_world_starts'",
    ).first() as { counter_value?: number } | null;
    return Math.max(0, Number(row?.counter_value || 0));
  } catch {
    // During first deployment the migration and Worker may overlap briefly.
    // Reads must remain available even if the metric table is not present yet.
    return 0;
  }
}

function directoryDescriptor(request: Request, env: any): Response {
  const base = new URL(request.url);
  base.pathname = '';
  base.search = '';
  base.hash = '';
  const origin = base.toString().replace(/\/$/, '');
  return new Response(JSON.stringify({
    format: 'dragonwilds-sync-public-directory-link',
    version: 1,
    name: 'Dragonwilds Sync Public Server Directory',
    api_base: origin,
    worlds_url: `${origin}/api/v1/worlds`,
    sources_url: `${origin}/api/v1/sources`,
    compatible_aliases: [`${origin}/worlds`, `${origin}/api/worlds`, `${origin}/manifest`],
    read_only: true,
    collection: {
      mode: 'resumable-full-scan',
      refresh: 'incremental-5-minute-cursor',
      sync_offline_retention_seconds: syncForgetSeconds(env),
    },
    presentation: {
      page_size: DIRECTORY_PAGE_SIZE,
      sync_first: true,
      offline_sync_category: true,
    },
    metrics: {
      total_sync_world_starts: 'directory.total_sync_world_starts',
    },
  }), {
    status: 200,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'cache-control': 'public, max-age=300',
      ...corsHeaders(),
    },
  });
}

function isWorldRead(pathname: string): boolean {
  return ['/api/v1/worlds', '/worlds', '/api/worlds', '/manifest'].includes(pathname);
}

async function decorateWorldListResponse(base: Response, env: any): Promise<Response> {
  if (!base.ok) return base;
  try {
    const payload = await base.clone().json() as Record<string, any>;
    if (!Array.isArray(payload?.worlds)) return base;

    const now = Math.floor(Date.now() / 1000);
    const retention = syncForgetSeconds(env);
    const sourceRows = payload.worlds.filter((row: unknown): row is Record<string, any> =>
      Boolean(row && typeof row === 'object' && !Array.isArray(row)));
    let forgottenSyncWorlds = 0;
    const worlds = sourceRows
      .filter((world) => {
        if (!isSyncWorld(world)) return true;
        const keep = syncWorldAge(world, now) <= retention;
        if (!keep) forgottenSyncWorlds += 1;
        return keep;
      })
      .map((world) => decorateWorld(world, now))
      .sort(compareDirectoryWorlds);

    const syncWorlds = worlds.filter(isSyncWorld);
    const syncOnline = syncWorlds.filter((world) => isOnlineStatus(world.status)).length;
    const syncOffline = syncWorlds.length - syncOnline;
    const starts = await totalSyncWorldStarts(env);
    const directory = payload.directory && typeof payload.directory === 'object' && !Array.isArray(payload.directory)
      ? payload.directory as Record<string, any>
      : {};
    const headers = new Headers(base.headers);
    headers.set('cache-control', 'public, max-age=30');

    return new Response(JSON.stringify({
      ...payload,
      worlds,
      directory: {
        ...directory,
        sync_worlds: syncWorlds.length,
        sync_online_worlds: syncOnline,
        sync_offline_worlds: syncOffline,
        forgotten_sync_worlds: forgottenSyncWorlds,
        sync_offline_retention_seconds: retention,
        total_sync_world_starts: starts,
        ordering: 'sync-first',
        page_size_hint: DIRECTORY_PAGE_SIZE,
      },
    }), {
      status: base.status,
      statusText: base.statusText,
      headers,
    });
  } catch {
    return base;
  }
}

async function decorateSingleWorldResponse(base: Response, env: any): Promise<Response> {
  if (!base.ok) return base;
  try {
    const world = await base.clone().json() as Record<string, any>;
    if (!world || typeof world !== 'object' || Array.isArray(world)) return base;
    const now = Math.floor(Date.now() / 1000);
    if (isSyncWorld(world) && syncWorldAge(world, now) > syncForgetSeconds(env)) {
      return new Response(JSON.stringify({ error: 'not_found' }), {
        status: 404,
        headers: {
          'content-type': 'application/json; charset=utf-8',
          'cache-control': 'no-store',
          ...corsHeaders(),
        },
      });
    }
    const headers = new Headers(base.headers);
    return new Response(JSON.stringify(decorateWorld(world, now)), {
      status: base.status,
      statusText: base.statusText,
      headers,
    });
  } catch {
    return base;
  }
}

function cleanWorldId(value: unknown): string {
  return String(value || '').trim().slice(0, 80).toLowerCase().replace(/[^a-z0-9._-]/g, '-');
}

function cleanStartId(payload: Record<string, any>): string {
  const value = payload.runtime_start_id ?? payload.runtime_session_id ?? payload.start_id ?? '';
  return String(value || '').trim().slice(0, 160).replace(/[^A-Za-z0-9._:-]/g, '-');
}

async function recordAcceptedSyncStart(env: any, payload: Record<string, any>): Promise<void> {
  const worldId = cleanWorldId(payload.world_id);
  if (!worldId) return;

  try {
    const now = Math.floor(Date.now() / 1000);
    const status = String(payload.status || 'online').trim().toLowerCase().slice(0, 24) || 'online';
    const explicitStartId = cleanStartId(payload);
    const state = await env.DB.prepare(`
      SELECT world_id, last_start_id, last_seen, last_status, starts
      FROM sync_world_start_state
      WHERE world_id = ?
    `).bind(worldId).first() as {
      world_id?: string;
      last_start_id?: string;
      last_seen?: number;
      last_status?: string;
      starts?: number;
    } | null;

    const hadState = Boolean(state?.world_id);
    const previousSeen = Number(state?.last_seen || 0);
    const previousStatus = String(state?.last_status || '').toLowerCase();
    const previousStartId = String(state?.last_start_id || '');
    const gapRestart = hadState && previousSeen > 0 && now - previousSeen > offlineAfterSeconds(env);
    const statusRestart = hadState && (
      (previousStatus === 'stopping' && status !== 'stopping') ||
      (status === 'starting' && previousStatus !== 'starting')
    );

    let shouldCount = !hadState || gapRestart || statusRestart;
    if (explicitStartId && previousStartId && explicitStartId !== previousStartId) shouldCount = true;

    // Migration 0004 seeds already-known Worlds with one historical start but
    // cannot know their current runtime token. The first token observed for a
    // still-running seeded World binds identity without double-counting it.
    const bindSeededTokenOnly = Boolean(
      hadState && explicitStartId && !previousStartId && !gapRestart && !statusRestart && Number(state?.starts || 0) > 0,
    );
    if (bindSeededTokenOnly) shouldCount = false;

    let counted = false;
    let eventStartId = explicitStartId;
    if (shouldCount) {
      eventStartId = explicitStartId || `legacy:${now}:${crypto.randomUUID()}`;
      const existingEvent = explicitStartId
        ? await env.DB.prepare(
          'SELECT 1 AS present FROM sync_world_start_events WHERE world_id = ? AND start_id = ?',
        ).bind(worldId, eventStartId).first() as { present?: number } | null
        : null;

      if (!existingEvent?.present) {
        const inserted = await env.DB.prepare(`
          INSERT OR IGNORE INTO sync_world_start_events (world_id, start_id, started_at)
          VALUES (?, ?, ?)
        `).bind(worldId, eventStartId, now).run();
        counted = Number((inserted as any)?.meta?.changes || 0) > 0;
      }
    }

    const nextStartId = explicitStartId || previousStartId || eventStartId || '';
    const nextStarts = Math.max(0, Number(state?.starts || 0)) + (counted ? 1 : 0);
    const statements = [
      env.DB.prepare(`
        INSERT INTO sync_world_start_state (
          world_id, last_start_id, last_seen, last_status, starts, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(world_id) DO UPDATE SET
          last_start_id = excluded.last_start_id,
          last_seen = excluded.last_seen,
          last_status = excluded.last_status,
          starts = excluded.starts,
          updated_at = excluded.updated_at
      `).bind(worldId, nextStartId, now, status, nextStarts, now),
    ];

    if (counted) {
      statements.push(env.DB.prepare(`
        INSERT INTO network_counters (counter_key, counter_value, updated_at)
        VALUES ('total_sync_world_starts', 1, ?)
        ON CONFLICT(counter_key) DO UPDATE SET
          counter_value = network_counters.counter_value + 1,
          updated_at = excluded.updated_at
      `).bind(now));
    }
    await env.DB.batch(statements);
  } catch (error) {
    // Start telemetry must never reject or delay an otherwise valid heartbeat.
    console.warn('Unable to update Sync World start metric', error);
  }
}

async function sourceResponseWithScanProgress(request: Request, env: any, ctx: ExecutionContext): Promise<Response> {
  ctx.waitUntil(scanPublicSourcesIncrementally(env, false));
  const base = await core.fetch(request, env, ctx);
  if (!base.ok) return base;
  try {
    const payload = await base.clone().json() as Record<string, unknown>;
    const scan = await publicScanStatus(env);
    const headers = new Headers(base.headers);
    headers.set('cache-control', 'public, max-age=30');
    return new Response(JSON.stringify({ ...payload, collection_mode: 'resumable-full-scan', scan }), {
      status: base.status,
      headers,
    });
  } catch {
    return base;
  }
}

export default {
  async fetch(request: Request, env: any, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === 'OPTIONS' && ['/worlds', '/api/worlds', '/manifest', '/directory-source.json'].includes(url.pathname)) {
      return new Response(null, { status: 204, headers: corsHeaders() });
    }

    if (request.method === 'GET' && url.pathname === '/directory-source.json') {
      return directoryDescriptor(request, env);
    }

    if (request.method === 'GET' && url.pathname === '/api/v1/sources') {
      return sourceResponseWithScanProgress(request, env, ctx);
    }

    if (request.method === 'GET' && isWorldRead(url.pathname)) {
      // Reads never scrape providers in the browser. They may nudge one bounded
      // background scan batch when the persisted scan state is due.
      ctx.waitUntil(scanPublicSourcesIncrementally(env, false));
      if (url.pathname !== '/api/v1/worlds') {
        url.pathname = '/api/v1/worlds';
        const forwarded = new Request(url.toString(), request);
        return decorateWorldListResponse(await core.fetch(forwarded, env, ctx), env);
      }
      return decorateWorldListResponse(await core.fetch(request, env, ctx), env);
    }

    if (request.method === 'GET' && url.pathname.startsWith('/api/v1/worlds/')) {
      return decorateSingleWorldResponse(await core.fetch(request, env, ctx), env);
    }

    if (request.method === 'POST' && url.pathname === '/api/v1/heartbeat') {
      let heartbeat: Record<string, any> = {};
      try {
        heartbeat = await request.clone().json() as Record<string, any>;
      } catch {
        // Core Worker returns the authoritative invalid-json response.
      }
      const response = await core.fetch(request, env, ctx);
      if (response.ok && heartbeat && typeof heartbeat === 'object') {
        ctx.waitUntil(recordAcceptedSyncStart(env, heartbeat));
      }
      return response;
    }

    return core.fetch(request, env, ctx);
  },

  async scheduled(_controller: ScheduledController, env: any, ctx: ExecutionContext): Promise<void> {
    // Do not call the older fixed-window source refresher here. This rotating
    // scan keeps a generation/cursor in D1 and retires stale rows only after a
    // complete provider pass, allowing the directory to grow beyond 500 rows.
    ctx.waitUntil(scanPublicSourcesIncrementally(env, true));
  },
};
