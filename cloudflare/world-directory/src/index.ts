interface Env {
  DB: D1Database;
  WORLD_SECRETS_JSON: string;
  OFFLINE_AFTER_SECONDS?: string;
  HISTORY_RETENTION_DAYS?: string;
}

type HeartbeatPayload = {
  world_id: string;
  world_name: string;
  description?: string;
  region?: string;
  version?: string;
  status?: "online" | "starting" | "stopping" | "maintenance";
  players?: { current?: number; max?: number };
  tags?: string[];
  mods?: string[];
  rules?: string[];
  badges?: string[];
  public_connect?: { host?: string; port?: number };
};

const encoder = new TextEncoder();

function json(data: unknown, status = 200, extraHeaders: HeadersInit = {}): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
      ...extraHeaders,
    },
  });
}

function publicCorsHeaders(): HeadersInit {
  return {
    "access-control-allow-origin": "*",
    "access-control-allow-methods": "GET, OPTIONS",
    "access-control-allow-headers": "content-type",
  };
}

function clampInt(value: unknown, fallback = 0, min = 0, max = 100000): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.min(max, Math.max(min, Math.trunc(parsed)));
}

function cleanText(value: unknown, max = 160): string {
  if (typeof value !== "string") return "";
  return value.trim().slice(0, max);
}

function cleanList(value: unknown, maxItems = 64, maxItemLength = 120): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter((item): item is string => typeof item === "string")
    .map((item) => item.trim().slice(0, maxItemLength))
    .filter(Boolean)
    .slice(0, maxItems);
}

function parseWorldSecrets(raw: string): Record<string, string> {
  try {
    const value: unknown = JSON.parse(raw);
    if (!value || typeof value !== "object" || Array.isArray(value)) return {};
    const secrets: Record<string, string> = {};
    for (const [key, secret] of Object.entries(value)) {
      if (typeof secret === "string" && secret.length >= 24) secrets[key] = secret;
    }
    return secrets;
  } catch {
    return {};
  }
}

async function hmacHex(secret: string, message: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const signature = await crypto.subtle.sign("HMAC", key, encoder.encode(message));
  return [...new Uint8Array(signature)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function timingSafeEqualHex(a: string, b: string): boolean {
  if (a.length !== b.length || a.length === 0) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i += 1) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

function normalizeHeartbeat(input: HeartbeatPayload): HeartbeatPayload {
  const worldId = cleanText(input.world_id, 80).toLowerCase().replace(/[^a-z0-9._-]/g, "-");
  const worldName = cleanText(input.world_name, 100);
  const current = clampInt(input.players?.current, 0, 0, 10000);
  const max = clampInt(input.players?.max, 0, 0, 10000);
  const status = ["online", "starting", "stopping", "maintenance"].includes(input.status || "")
    ? input.status
    : "online";

  return {
    world_id: worldId,
    world_name: worldName,
    description: cleanText(input.description, 500),
    region: cleanText(input.region, 80),
    version: cleanText(input.version, 64),
    status,
    players: {
      current: max > 0 ? Math.min(current, max) : current,
      max,
    },
    tags: cleanList(input.tags, 24, 48),
    mods: cleanList(input.mods, 128, 120),
    rules: cleanList(input.rules, 64, 180),
    badges: cleanList(input.badges, 24, 48),
    public_connect: {
      host: cleanText(input.public_connect?.host, 255),
      port: input.public_connect?.port
        ? clampInt(input.public_connect.port, 0, 1, 65535)
        : undefined,
    },
  };
}

async function handleHeartbeat(request: Request, env: Env): Promise<Response> {
  const contentLength = Number(request.headers.get("content-length") || "0");
  if (contentLength > 32768) return json({ error: "payload_too_large" }, 413);

  const timestamp = request.headers.get("x-dws-timestamp") || "";
  const suppliedSignature = (request.headers.get("x-dws-signature") || "").toLowerCase();
  const timestampSeconds = Number(timestamp);
  const nowSeconds = Math.floor(Date.now() / 1000);

  if (!Number.isFinite(timestampSeconds) || Math.abs(nowSeconds - timestampSeconds) > 300) {
    return json({ error: "stale_or_invalid_timestamp" }, 401);
  }

  const rawBody = await request.text();
  if (rawBody.length > 32768) return json({ error: "payload_too_large" }, 413);

  let parsed: HeartbeatPayload;
  try {
    parsed = JSON.parse(rawBody) as HeartbeatPayload;
  } catch {
    return json({ error: "invalid_json" }, 400);
  }

  const payload = normalizeHeartbeat(parsed);
  if (!payload.world_id || !payload.world_name) {
    return json({ error: "world_id_and_world_name_required" }, 400);
  }

  const secrets = parseWorldSecrets(env.WORLD_SECRETS_JSON || "{}");
  const worldSecret = secrets[payload.world_id];
  if (!worldSecret) return json({ error: "unknown_world" }, 401);

  const expectedSignature = await hmacHex(worldSecret, `${timestamp}.${rawBody}`);
  if (!timingSafeEqualHex(expectedSignature, suppliedSignature)) {
    return json({ error: "invalid_signature" }, 401);
  }

  const now = Math.floor(Date.now() / 1000);
  const existing = await env.DB.prepare("SELECT last_seen FROM worlds WHERE world_id = ?")
    .bind(payload.world_id)
    .first<{ last_seen: number }>();

  if (existing?.last_seen && now - existing.last_seen < 15) {
    return json({ error: "heartbeat_too_frequent" }, 429);
  }

  const playersCurrent = payload.players?.current || 0;
  const playersMax = payload.players?.max || 0;
  const status = payload.status || "online";
  const connectHost = payload.public_connect?.host || "";
  const connectPort = payload.public_connect?.port || null;

  await env.DB.batch([
    env.DB.prepare(`
      INSERT INTO worlds (
        world_id, world_name, description, region, version, status,
        players_current, players_max, tags_json, mods_json, rules_json,
        badges_json, public_connect_host, public_connect_port,
        is_listed, last_seen, updated_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
      ON CONFLICT(world_id) DO UPDATE SET
        world_name = excluded.world_name,
        description = excluded.description,
        region = excluded.region,
        version = excluded.version,
        status = excluded.status,
        players_current = excluded.players_current,
        players_max = excluded.players_max,
        tags_json = excluded.tags_json,
        mods_json = excluded.mods_json,
        rules_json = excluded.rules_json,
        badges_json = excluded.badges_json,
        public_connect_host = excluded.public_connect_host,
        public_connect_port = excluded.public_connect_port,
        last_seen = excluded.last_seen,
        updated_at = excluded.updated_at
    `).bind(
      payload.world_id,
      payload.world_name,
      payload.description || "",
      payload.region || "",
      payload.version || "",
      status,
      playersCurrent,
      playersMax,
      JSON.stringify(payload.tags || []),
      JSON.stringify(payload.mods || []),
      JSON.stringify(payload.rules || []),
      JSON.stringify(payload.badges || []),
      connectHost,
      connectPort,
      now,
      now,
    ),
    env.DB.prepare(`
      INSERT OR IGNORE INTO heartbeat_history
        (world_id, seen_at, status, players_current, players_max, version)
      VALUES (?, ?, ?, ?, ?, ?)
    `).bind(payload.world_id, now, status, playersCurrent, playersMax, payload.version || ""),
  ]);

  const retentionDays = clampInt(env.HISTORY_RETENTION_DAYS, 7, 1, 90);
  const cutoff = now - retentionDays * 86400;
  await env.DB.prepare("DELETE FROM heartbeat_history WHERE seen_at < ?").bind(cutoff).run();

  return json({ ok: true, world_id: payload.world_id, accepted_at: now });
}

function parseJsonArray(value: unknown): string[] {
  if (typeof value !== "string") return [];
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed.filter((v): v is string => typeof v === "string") : [];
  } catch {
    return [];
  }
}

function publicWorld(row: Record<string, unknown>, offlineAfterSeconds: number): Record<string, unknown> {
  const lastSeen = Number(row.last_seen || 0);
  const age = Math.max(0, Math.floor(Date.now() / 1000) - lastSeen);
  const isOffline = !lastSeen || age > offlineAfterSeconds;

  return {
    world_id: row.world_id,
    world_name: row.world_name,
    description: row.description || "",
    region: row.region || "",
    version: row.version || "",
    status: isOffline ? "offline" : row.status || "online",
    players: {
      current: Number(row.players_current || 0),
      max: Number(row.players_max || 0),
    },
    tags: parseJsonArray(row.tags_json),
    mods: parseJsonArray(row.mods_json),
    rules: parseJsonArray(row.rules_json),
    badges: parseJsonArray(row.badges_json),
    public_connect: row.public_connect_host
      ? {
          host: row.public_connect_host,
          port: row.public_connect_port ? Number(row.public_connect_port) : null,
        }
      : null,
    last_seen: lastSeen,
    heartbeat_age_seconds: age,
    source_name: "Dragonwilds Sync",
    directory_source: "dragonwilds-sync",
    is_sync_world: true,
    host_type: "dedicated",
    classification: {
      host_type: "dedicated",
      visibility: "public",
    },
    sources: [{ id: "dragonwilds-sync", label: "Dragonwilds Sync signed heartbeat" }],
  };
}

async function collectSyncWorlds(env: Env): Promise<Array<Record<string, unknown>>> {
  const offlineAfter = clampInt(env.OFFLINE_AFTER_SECONDS, 1800, 60, 86400);
  const result = await env.DB.prepare(`
    SELECT * FROM worlds
    WHERE is_listed = 1
    ORDER BY last_seen DESC, world_name COLLATE NOCASE ASC
  `).all<Record<string, unknown>>();

  const worlds = (result.results || []).map((row) => publicWorld(row, offlineAfter));
  worlds.sort((a, b) => {
    const aStatus = String(a.status || "");
    const bStatus = String(b.status || "");
    const aOnline = ["online", "starting", "maintenance"].includes(aStatus);
    const bOnline = ["online", "starting", "maintenance"].includes(bStatus);
    if (aOnline !== bOnline) return Number(bOnline) - Number(aOnline);
    const seenDiff = Number(b.last_seen || 0) - Number(a.last_seen || 0);
    if (seenDiff) return seenDiff;
    return String(a.world_name || "").localeCompare(String(b.world_name || ""));
  });
  return worlds;
}

async function listWorlds(env: Env): Promise<Response> {
  const worlds = await collectSyncWorlds(env);
  return json(
    {
      generated_at: Math.floor(Date.now() / 1000),
      worlds,
      directory: {
        sync_worlds: worlds.length,
        source: "dragonwilds-sync-heartbeats",
        public_source_aggregation: false,
      },
    },
    200,
    { ...publicCorsHeaders(), "cache-control": "public, max-age=30" },
  );
}

async function getWorld(env: Env, worldId: string): Promise<Response> {
  const worlds = await collectSyncWorlds(env);
  const world = worlds.find((entry) => String(entry.world_id) === worldId);
  if (!world) return json({ error: "not_found" }, 404, publicCorsHeaders());
  return json(world, 200, {
    ...publicCorsHeaders(),
    "cache-control": "public, max-age=30",
  });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: publicCorsHeaders() });
    }

    if (request.method === "GET" && url.pathname === "/health") {
      return json({
        ok: true,
        service: "dragonwilds-sync-directory",
        mode: "sync-heartbeats-only",
        public_source_aggregation: false,
        public_sources: [],
      }, 200, publicCorsHeaders());
    }

    if (request.method === "GET" && url.pathname === "/api/v1/worlds") {
      return listWorlds(env);
    }

    if (request.method === "GET" && url.pathname.startsWith("/api/v1/worlds/")) {
      const worldId = decodeURIComponent(url.pathname.slice("/api/v1/worlds/".length));
      return getWorld(env, worldId);
    }

    if (request.method === "POST" && url.pathname === "/api/v1/heartbeat") {
      return handleHeartbeat(request, env);
    }

    return json({ error: "not_found" }, 404, request.method === "GET" ? publicCorsHeaders() : {});
  },
};
