import coreWorker from './index';

const core = coreWorker as any;
const DEFAULT_OFFLINE_AFTER_SECONDS = 30 * 60;

function clampInt(value: unknown, fallback: number, min: number, max: number): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.min(max, Math.max(min, Math.trunc(parsed)));
}

function offlineAfterSeconds(env: any): number {
  return clampInt(env?.OFFLINE_AFTER_SECONDS, DEFAULT_OFFLINE_AFTER_SECONDS, 60, 86400);
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
    console.warn('Unable to update Sync World start metric', error);
  }
}

export default {
  async fetch(request: Request, env: any, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

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
};
