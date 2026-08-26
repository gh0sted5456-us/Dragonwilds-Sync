interface Env {
  DB: D1Database;
  WORLD_SECRETS_JSON?: string;
  OFFLINE_AFTER_SECONDS?: string;
  HISTORY_RETENTION_DAYS?: string;
  REGISTRATION_RETENTION_DAYS?: string;
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
  host_os?: string;
  host_os_label?: string;
  password_required?: boolean;
  mod_summary?: Array<Record<string, unknown>>;
  runtime_stack?: Record<string, unknown>;
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

function cleanChannel(value: unknown): string {
  const channel = cleanText(value, 24).toLowerCase();
  return ["baseline", "stable", "experimental", "release-candidate"].includes(channel) ? channel : "unknown";
}

function cleanModSummary(value: unknown): Array<Record<string, unknown>> {
  if (!Array.isArray(value)) return [];
  return value.filter((row): row is Record<string, unknown> => Boolean(row) && typeof row === "object" && !Array.isArray(row))
    .slice(0, 128).map((row) => ({
      key: cleanText(row.key, 100),
      name: cleanText(row.name, 120),
      loader: cleanText(row.loader ?? row.section ?? row.category, 40).toLowerCase(),
      classification: cleanText(row.classification ?? row.distribution, 40).toLowerCase(),
      client_required: row.client_required === true || row.distribution === "client_required" || row.classification === "player_required",
      version: cleanText(row.version, 64),
    })).filter((row) => row.name || row.key);
}

function filterMetadata(input: HeartbeatPayload): Record<string, unknown> {
  const stack = input.runtime_stack && typeof input.runtime_stack === "object" ? input.runtime_stack : {};
  const ue4ss = stack.ue4ss && typeof stack.ue4ss === "object" ? stack.ue4ss as Record<string, unknown> : {};
  const runeschema = stack.runeschema && typeof stack.runeschema === "object" ? stack.runeschema as Record<string, unknown> : {};
  const sync = stack.dragonwilds_sync && typeof stack.dragonwilds_sync === "object" ? stack.dragonwilds_sync as Record<string, unknown> : {};
  const game = stack.dragonwilds && typeof stack.dragonwilds === "object" ? stack.dragonwilds as Record<string, unknown> : {};
  return {
    host_os: cleanText(input.host_os, 40).toLowerCase(),
    host_os_label: cleanText(input.host_os_label, 100),
    password_required: input.password_required === true,
    mod_summary: cleanModSummary(input.mod_summary),
    runtime_channels: {
      ue4ss: cleanChannel(ue4ss.channel),
      runeschema: cleanChannel(runeschema.channel),
      sync: cleanChannel(sync.channel),
    },
    server_current: typeof game.server_current === "boolean" ? game.server_current : null,
    server_cl_status: cleanText(game.server_cl_status, 24).toLowerCase(),
  };
}

function registrationRetentionSeconds(env: Env): number {
  return clampInt(env.REGISTRATION_RETENTION_DAYS, 30, 1, 365) * 86400;
}

async function purgeStaleRegistrations(env: Env, now = Math.floor(Date.now() / 1000)): Promise<void> {
  const cutoff = now - registrationRetentionSeconds(env);
  await env.DB.batch([
    env.DB.prepare("DELETE FROM heartbeat_history WHERE world_id IN (SELECT world_id FROM worlds WHERE last_seen < ?)").bind(cutoff),
    env.DB.prepare("DELETE FROM worlds WHERE last_seen < ?").bind(cutoff),
    env.DB.prepare("DELETE FROM world_publishers WHERE last_seen < ?").bind(cutoff),
  ]);
}

function decodeBase64(value: string): Uint8Array | null {
  try {
    const raw = atob(value);
    const result = new Uint8Array(raw.length);
    for (let index = 0; index < raw.length; index += 1) result[index] = raw.charCodeAt(index);
    return result;
  } catch {
    return null;
  }
}

async function sha256Hex(value: Uint8Array): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", value.buffer as ArrayBuffer);
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function authenticatePublisher(
  request: Request,
  env: Env,
  timestamp: string,
  rawBody: string,
  worldId: string,
): Promise<{ ok: true; mode: string; operatorFingerprint: string } | { ok: false; response: Response }> {
  const suppliedSignature = request.headers.get("x-dws-signature") || "";
  const publicKeyText = request.headers.get("x-dws-public-key") || "";
  const operatorFingerprint = (request.headers.get("x-dws-operator") || "").toLowerCase();
  const publicKey = decodeBase64(publicKeyText);
  const signature = decodeBase64(suppliedSignature);

  if (publicKey?.length === 32 && signature?.length === 64 && /^dwo1-[0-9a-f]{24}$/.test(operatorFingerprint)) {
    const expectedFingerprint = `dwo1-${(await sha256Hex(publicKey)).slice(0, 24)}`;
    if (expectedFingerprint !== operatorFingerprint) {
      return { ok: false, response: json({ error: "operator_fingerprint_mismatch" }, 401) };
    }
    try {
      const key = await crypto.subtle.importKey("raw", publicKey.buffer as ArrayBuffer, { name: "Ed25519" }, false, ["verify"]);
      const verified = await crypto.subtle.verify(
        { name: "Ed25519" }, key, signature.buffer as ArrayBuffer, encoder.encode(`${timestamp}.${rawBody}`),
      );
      if (!verified) return { ok: false, response: json({ error: "invalid_signature" }, 401) };
    } catch {
      return { ok: false, response: json({ error: "unsupported_or_invalid_operator_key" }, 401) };
    }

    const existing = await env.DB.prepare(
      "SELECT operator_fingerprint, public_key FROM world_publishers WHERE world_id = ?",
    ).bind(worldId).first<{ operator_fingerprint: string; public_key: string }>();
    if (existing && (existing.operator_fingerprint !== operatorFingerprint || existing.public_key !== publicKeyText)) {
      return { ok: false, response: json({ error: "world_ownership_conflict" }, 409) };
    }
    const now = Math.floor(Date.now() / 1000);
    await env.DB.prepare(`
      INSERT INTO world_publishers (world_id, operator_fingerprint, public_key, registered_at, last_seen)
      VALUES (?, ?, ?, ?, ?)
      ON CONFLICT(world_id) DO UPDATE SET last_seen = excluded.last_seen
    `).bind(worldId, operatorFingerprint, publicKeyText, now, now).run();
    return { ok: true, mode: "ed25519-self-registration", operatorFingerprint };
  }

  // Compatibility for explicitly provisioned pre-V3 publishers.
  const secrets = parseWorldSecrets(env.WORLD_SECRETS_JSON || "{}");
  const worldSecret = secrets[worldId];
  const legacySignature = (request.headers.get("x-dws-legacy-signature") || suppliedSignature).toLowerCase();
  if (worldSecret) {
    const expected = await hmacHex(worldSecret, `${timestamp}.${rawBody}`);
    if (timingSafeEqualHex(expected, legacySignature)) {
      return { ok: true, mode: "legacy-hmac", operatorFingerprint: "" };
    }
  }
  return { ok: false, response: json({ error: "publisher_identity_required" }, 401) };
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

  // Expired ownership must be removed before authentication so a World that has
  // been offline for the full retention window can register cleanly again.
  await purgeStaleRegistrations(env, nowSeconds);
  const publisher = await authenticatePublisher(request, env, timestamp, rawBody, payload.world_id);
  if (!publisher.ok) return publisher.response;

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
  const metadataJson = JSON.stringify(filterMetadata(parsed));

  await env.DB.batch([
    env.DB.prepare(`
      INSERT INTO worlds (
        world_id, world_name, description, region, version, status,
        players_current, players_max, tags_json, mods_json, rules_json,
        badges_json, public_connect_host, public_connect_port,
        is_listed, last_seen, updated_at, metadata_json
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
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
        metadata_json = excluded.metadata_json,
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
      metadataJson,
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

  return json({
    ok: true,
    world_id: payload.world_id,
    accepted_at: now,
    registration: publisher.mode,
    operator_fingerprint: publisher.operatorFingerprint,
  });
}

async function handleDeregister(request: Request, env: Env, pathWorldId: string): Promise<Response> {
  const contentLength = Number(request.headers.get("content-length") || "0");
  if (contentLength > 4096) return json({ error: "payload_too_large" }, 413);
  const timestamp = request.headers.get("x-dws-timestamp") || "";
  const timestampSeconds = Number(timestamp);
  const now = Math.floor(Date.now() / 1000);
  if (!Number.isFinite(timestampSeconds) || Math.abs(now - timestampSeconds) > 300) {
    return json({ error: "stale_or_invalid_timestamp" }, 401);
  }
  const rawBody = await request.text();
  let parsed: Record<string, unknown>;
  try {
    parsed = JSON.parse(rawBody) as Record<string, unknown>;
  } catch {
    return json({ error: "invalid_json" }, 400);
  }
  const worldId = cleanText(pathWorldId, 80).toLowerCase().replace(/[^a-z0-9._-]/g, "-");
  const bodyWorldId = cleanText(parsed.world_id, 80).toLowerCase().replace(/[^a-z0-9._-]/g, "-");
  if (!worldId || bodyWorldId !== worldId) return json({ error: "world_id_mismatch" }, 400);

  await purgeStaleRegistrations(env, now);
  const publisher = await authenticatePublisher(request, env, timestamp, rawBody, worldId);
  if (!publisher.ok) return publisher.response;
  await env.DB.batch([
    env.DB.prepare("DELETE FROM heartbeat_history WHERE world_id = ?").bind(worldId),
    env.DB.prepare("DELETE FROM worlds WHERE world_id = ?").bind(worldId),
    env.DB.prepare("DELETE FROM world_publishers WHERE world_id = ?").bind(worldId),
  ]);
  return json({ ok: true, world_id: worldId, deregistered_at: now });
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

function parseJsonObject(value: unknown): Record<string, unknown> {
  if (typeof value !== "string") return {};
  try {
    const parsed = JSON.parse(value);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
  } catch {
    return {};
  }
}

function publicWorld(row: Record<string, unknown>, offlineAfterSeconds: number): Record<string, unknown> {
  const lastSeen = Number(row.last_seen || 0);
  const age = Math.max(0, Math.floor(Date.now() / 1000) - lastSeen);
  const isOffline = !lastSeen || age > offlineAfterSeconds;

  const metadata = parseJsonObject(row.metadata_json);
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
    host_os: metadata.host_os || "",
    host_os_label: metadata.host_os_label || "",
    password_required: metadata.password_required === true,
    mod_summary: Array.isArray(metadata.mod_summary) ? metadata.mod_summary : [],
    runtime_channels: metadata.runtime_channels || {},
    server_current: typeof metadata.server_current === "boolean" ? metadata.server_current : null,
    server_cl_status: metadata.server_cl_status || "unknown",
    public_connect: row.public_connect_host
      ? {
          host: row.public_connect_host,
          port: row.public_connect_port ? Number(row.public_connect_port) : null,
        }
      : null,
    external_ip: row.public_connect_host || "",
    internal_ip: "",
    sync_port: row.public_connect_port ? Number(row.public_connect_port) : 27051,
    game_port: 7777,
    fingerprint: row.world_id,
    fingerprint_claimed: row.world_id,
    protocol: "dragonwilds-world-sync",
    sync_protocol: "dragonwilds-world-sync",
    sync_ready: true,
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
  const registrationCutoff = Math.floor(Date.now() / 1000) - registrationRetentionSeconds(env);
  const result = await env.DB.prepare(`
    SELECT * FROM worlds
    WHERE is_listed = 1 AND last_seen >= ?
    ORDER BY last_seen DESC, world_name COLLATE NOCASE ASC
  `).bind(registrationCutoff).all<Record<string, unknown>>();

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

    if (request.method === "DELETE" && url.pathname.startsWith("/api/v1/worlds/")) {
      const worldId = decodeURIComponent(url.pathname.slice("/api/v1/worlds/".length));
      return handleDeregister(request, env, worldId);
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
  async scheduled(_controller: ScheduledController, env: Env): Promise<void> {
    await purgeStaleRegistrations(env);
  },
};
