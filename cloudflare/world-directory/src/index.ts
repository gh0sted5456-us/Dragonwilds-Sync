interface Env {
  DB: D1Database;
  WORLD_SECRETS_JSON: string;
  OFFLINE_AFTER_SECONDS?: string;
  HISTORY_RETENTION_DAYS?: string;
  PUBLIC_SOURCE_REFRESH_SECONDS?: string;
  PUBLIC_SOURCE_MAX_SERVERS?: string;
  PUBLIC_SOURCE_PROVIDERS?: string;
  PUBLIC_SOURCE_TIMEOUT_MS?: string;
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

type SourceRecord = {
  sourceId: string;
  sourceWorldId: string;
  sourceName: string;
  sourceUrl: string;
  worldName: string;
  serverName: string;
  description: string;
  region: string;
  countryCode: string;
  countryName: string;
  version: string;
  status: string;
  playersCurrent: number;
  playersMax: number;
  tags: string[];
  badges: string[];
  publicConnectHost: string;
  publicConnectPort: number | null;
  passwordProtected: boolean;
  firstSeen: number;
  lastSeen: number;
  metadata: Record<string, unknown>;
};

const encoder = new TextEncoder();
const SHRUG_API_URL = "https://shrug.games/api/rsdw/servers";
const SHRUG_SITE_URL = "https://shrug.games/games/runescape-dragonwilds/servers/";
const LOBBYSUP_API_URL = "https://www.lobbysup.com/api/servers/dragonwilds";
const LOBBYSUP_SITE_URL = "https://www.lobbysup.com/dragonwilds";

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
      if (typeof secret === "string" && secret.length >= 24) {
        secrets[key] = secret;
      }
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

function parseJsonObject(value: unknown): Record<string, unknown> {
  if (typeof value !== "string") return {};
  try {
    const parsed = JSON.parse(value);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed as Record<string, unknown> : {};
  } catch {
    return {};
  }
}

function publicWorld(row: Record<string, unknown>, offlineAfterSeconds: number): Record<string, any> {
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
    public_connect:
      row.public_connect_host
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

function normalizeHost(value: unknown): string {
  const raw = cleanText(value, 255).toLowerCase();
  if (!raw) return "";
  return raw.startsWith("[") && raw.endsWith("]") ? raw.slice(1, -1) : raw.replace(/\.$/, "");
}

function endpointKey(host: unknown, port: unknown): string {
  const normalizedHost = normalizeHost(host);
  const normalizedPort = clampInt(port, 0, 0, 65535);
  return normalizedHost && normalizedPort ? `${normalizedHost}:${normalizedPort}` : "";
}

function nameKey(value: unknown): string {
  return cleanText(value, 100).toLocaleLowerCase("en-US");
}

function versionKey(value: unknown): string {
  return cleanText(value, 64).toLocaleLowerCase("en-US").replace(/^cl[-\s]*/i, "cl-");
}

function stableHash(value: string): string {
  let a = 0x811c9dc5;
  let b = 0x9e3779b9;
  for (let i = 0; i < value.length; i += 1) {
    const code = value.charCodeAt(i);
    a = Math.imul(a ^ code, 0x01000193);
    b = Math.imul(b ^ (code + i), 0x85ebca6b);
  }
  return `${(a >>> 0).toString(16).padStart(8, "0")}${(b >>> 0).toString(16).padStart(8, "0")}`;
}

function decodeHtml(value: string): string {
  return value
    .replace(/<br\s*\/?>/gi, " ")
    .replace(/<[^>]*>/g, " ")
    .replace(/&nbsp;|&#160;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/&quot;|&#34;/gi, "\"")
    .replace(/&#39;|&apos;/gi, "'")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">")
    .replace(/\s+/g, " ")
    .trim();
}

function extractClassText(fragment: string, className: string): string {
  const escaped = className.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const pattern = new RegExp(
    `<[^>]*class=["'][^"']*\\b${escaped}\\b[^"']*["'][^>]*>([\\s\\S]*?)<\\/[^>]+>`,
    "i",
  );
  return decodeHtml(pattern.exec(fragment)?.[1] || "");
}

function extractDifficulty(fragment: string): string {
  const match = /<[^>]*class=["'][^"']*\bsb-badge--diff-[^"']*["'][^>]*>([\s\S]*?)<\/[^>]+>/i.exec(fragment);
  return decodeHtml(match?.[1] || "");
}

function hasClass(fragment: string, className: string): boolean {
  const escaped = className.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`class=["'][^"']*\\b${escaped}\\b[^"']*["']`, "i").test(fragment);
}

function parseShrugRows(payload: string): Array<Record<string, unknown>> {
  const chunks = payload
    .split(/<div\b[^>]*class=["'][^"']*\bsb-row\b[^"']*["'][^>]*>/gi)
    .slice(1);
  const rows: Array<Record<string, unknown>> = [];

  for (const chunk of chunks) {
    const serverName = extractClassText(chunk, "sb-server-name");
    const worldName = extractClassText(chunk, "sb-world-name");
    if (!serverName && !worldName) continue;

    const playerText = extractClassText(chunk, "sb-player-count");
    const players = /(\d+)\s*\/\s*(\d+)/.exec(playerText);
    const build = extractClassText(chunk, "sb-row-build").replace(/^CL-/i, "").trim();
    rows.push({
      serverName,
      worldName,
      difficulty: extractDifficulty(chunk),
      pvp: hasClass(chunk, "sb-badge--pvp"),
      locked: hasClass(chunk, "sb-badge--locked"),
      players: players ? Number(players[1]) : 0,
      maxPlayers: players ? Number(players[2]) : 0,
      build,
    });
  }

  return rows;
}

function parseAddress(value: unknown): { host: string; port: number } {
  const address = cleanText(value, 320);
  if (!address) return { host: "", port: 7777 };

  if (address.startsWith("[")) {
    const close = address.indexOf("]");
    if (close > 1) {
      const host = address.slice(1, close);
      const port = address.slice(close + 1).replace(/^:/, "");
      return { host, port: clampInt(port, 7777, 1, 65535) };
    }
  }

  const split = address.lastIndexOf(":");
  if (split > 0 && address.indexOf(":") === split) {
    return {
      host: address.slice(0, split),
      port: clampInt(address.slice(split + 1), 7777, 1, 65535),
    };
  }

  return { host: address, port: 7777 };
}

function parseRemoteTimestamp(value: unknown, fallback: number): number {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value > 1e12 ? Math.floor(value / 1000) : Math.floor(value);
  }
  if (typeof value === "string" && value.trim()) {
    const parsed = Date.parse(value);
    if (Number.isFinite(parsed)) return Math.floor(parsed / 1000);
  }
  return fallback;
}

async function fetchWithTimeout(url: string, timeoutMs: number, accept: string): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, {
      headers: {
        "accept": accept,
        "user-agent": "DragonwildsSync-Directory/2.0 (+public-world-browser)",
      },
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timer);
  }
}

async function fetchShrugSource(env: Env): Promise<SourceRecord[]> {
  const maxServers = clampInt(env.PUBLIC_SOURCE_MAX_SERVERS, 100, 10, 500);
  const timeoutMs = clampInt(env.PUBLIC_SOURCE_TIMEOUT_MS, 5000, 1000, 15000);
  const offsets = Array.from({ length: Math.ceil(maxServers / 10) }, (_, index) => index * 10);
  const pages = await Promise.allSettled(offsets.map(async (offset) => {
    const url = `${SHRUG_API_URL}?offset=${offset}&sort=players`;
    const response = await fetchWithTimeout(url, timeoutMs, "text/html");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return parseShrugRows(await response.text());
  }));

  const now = Math.floor(Date.now() / 1000);
  const rows = pages.flatMap((page) => page.status === "fulfilled" ? page.value : []);
  if (!rows.length) {
    const errors = pages
      .filter((page): page is PromiseRejectedResult => page.status === "rejected")
      .map((page) => String(page.reason))
      .slice(0, 3);
    throw new Error(`Shrug EOS mirror returned no usable rows${errors.length ? ` (${errors.join("; ")})` : ""}`);
  }

  const seen = new Set<string>();
  const records: SourceRecord[] = [];
  for (const row of rows) {
    const serverName = cleanText(row.serverName, 100);
    const worldName = cleanText(row.worldName || row.serverName, 100) || "Dragonwilds World";
    const build = cleanText(row.build, 64).replace(/^CL-/i, "");
    const identity = `${serverName.toLocaleLowerCase("en-US")}|${worldName.toLocaleLowerCase("en-US")}|${build}`;
    const sourceWorldId = stableHash(identity);
    if (seen.has(sourceWorldId)) continue;
    seen.add(sourceWorldId);

    const difficulty = cleanText(row.difficulty, 40);
    const tags = ["DEDICATED", "EOS", ...(difficulty ? [difficulty.toUpperCase()] : [])];
    if (row.pvp) tags.push("PVP");
    if (row.locked) tags.push("PASSWORD");

    records.push({
      sourceId: "shrug-eos-index",
      sourceWorldId,
      sourceName: "Dragonwilds EOS session mirror",
      sourceUrl: SHRUG_SITE_URL,
      worldName,
      serverName,
      description: `Public Dragonwilds session${build ? ` · CL-${build}` : ""}`,
      region: "",
      countryCode: "",
      countryName: "",
      version: build ? `CL-${build}` : "",
      status: "online",
      playersCurrent: clampInt(row.players, 0, 0, 10000),
      playersMax: clampInt(row.maxPlayers, 0, 0, 10000),
      tags,
      badges: ["PUBLIC SERVER"],
      publicConnectHost: "",
      publicConnectPort: null,
      passwordProtected: Boolean(row.locked),
      firstSeen: now,
      lastSeen: now,
      metadata: {
        provider: "shrug-eos-index",
        official: false,
        session_api: "eos",
        server_name: serverName,
        build,
      },
    });
    if (records.length >= maxServers) break;
  }

  return records;
}

async function fetchLobbySupSource(env: Env): Promise<SourceRecord[]> {
  const maxServers = clampInt(env.PUBLIC_SOURCE_MAX_SERVERS, 100, 10, 500);
  const timeoutMs = clampInt(env.PUBLIC_SOURCE_TIMEOUT_MS, 5000, 1000, 15000);
  const response = await fetchWithTimeout(LOBBYSUP_API_URL, timeoutMs, "application/json");
  if (!response.ok) throw new Error(`HTTP ${response.status}`);

  const payload: unknown = await response.json();
  const source = payload && typeof payload === "object" && !Array.isArray(payload)
    ? (payload as Record<string, unknown>).servers
    : payload;
  const rows = Array.isArray(source) ? source.filter((row): row is Record<string, unknown> =>
    Boolean(row && typeof row === "object" && !Array.isArray(row))) : [];
  if (!rows.length) throw new Error("LobbySup returned no usable rows");

  const now = Math.floor(Date.now() / 1000);
  const records: SourceRecord[] = [];
  const seen = new Set<string>();

  for (const row of rows.slice(0, maxServers)) {
    const address = cleanText(row.address, 320);
    const { host, port } = parseAddress(address);
    const worldName = cleanText(row.name, 100) || "Dragonwilds World";
    const sourceWorldId = stableHash(`${worldName.toLocaleLowerCase("en-US")}|${normalizeHost(host)}|${port}`);
    if (seen.has(sourceWorldId)) continue;
    seen.add(sourceWorldId);

    const countryCode = cleanText(row.countryCode, 2).toUpperCase();
    const countryName = cleanText(row.country, 80);
    const online = row.online === undefined ? true : Boolean(row.online);
    const firstSeen = parseRemoteTimestamp(row.firstSeen, now);
    const lastSeen = parseRemoteTimestamp(row.lastSeen ?? row.lastUpdated, now);

    records.push({
      sourceId: "lobbysup",
      sourceWorldId,
      sourceName: "LobbySup public observations",
      sourceUrl: LOBBYSUP_SITE_URL,
      worldName,
      serverName: worldName,
      description: "Public Dragonwilds server observed by LobbySup",
      region: countryName,
      countryCode,
      countryName,
      version: cleanText(row.version ?? row.build, 64),
      status: online ? "online" : "offline",
      playersCurrent: clampInt(row.players, 0, 0, 10000),
      playersMax: clampInt(row.maxPlayers, 0, 0, 10000),
      tags: ["DRAGONWILDS", "PUBLIC"],
      badges: ["PUBLIC SERVER"],
      publicConnectHost: host,
      publicConnectPort: host ? port : null,
      passwordProtected: Boolean(row.locked ?? row.passwordProtected),
      firstSeen,
      lastSeen: online ? Math.max(lastSeen, now - 60) : lastSeen,
      metadata: {
        provider: "lobbysup",
        official: false,
        address,
        map: cleanText(row.map, 80),
        first_seen: cleanText(row.firstSeen, 64),
        last_seen: cleanText(row.lastSeen, 64),
        last_updated: cleanText(row.lastUpdated, 64),
        latitude: typeof row.lat === "number" ? row.lat : null,
        longitude: typeof row.lon === "number" ? row.lon : null,
      },
    });
  }

  return records;
}

function enabledProviders(env: Env): Set<string> {
  const configured = cleanText(env.PUBLIC_SOURCE_PROVIDERS || "shrug,lobbysup", 120)
    .split(",")
    .map((value) => value.trim().toLowerCase())
    .filter(Boolean);
  return new Set(configured);
}

async function recordSourceRun(env: Env, sourceId: string, success: boolean, count: number, error = ""): Promise<void> {
  const now = Math.floor(Date.now() / 1000);
  await env.DB.prepare(`
    INSERT INTO public_source_runs (source_id, last_attempt_at, last_success_at, last_error, last_count)
    VALUES (?, ?, ?, ?, ?)
    ON CONFLICT(source_id) DO UPDATE SET
      last_attempt_at = excluded.last_attempt_at,
      last_success_at = CASE WHEN excluded.last_success_at > 0 THEN excluded.last_success_at ELSE public_source_runs.last_success_at END,
      last_error = excluded.last_error,
      last_count = CASE WHEN excluded.last_success_at > 0 THEN excluded.last_count ELSE public_source_runs.last_count END
  `).bind(sourceId, now, success ? now : 0, cleanText(error, 500), count).run();
}

async function saveSourceRecords(env: Env, sourceId: string, records: SourceRecord[]): Promise<void> {
  if (!records.length) throw new Error(`${sourceId} refresh produced zero records`);
  const refreshToken = crypto.randomUUID();
  const now = Math.floor(Date.now() / 1000);

  for (let offset = 0; offset < records.length; offset += 35) {
    const chunk = records.slice(offset, offset + 35);
    await env.DB.batch(chunk.map((record) =>
      env.DB.prepare(`
        INSERT INTO public_source_worlds (
          source_id, source_world_id, source_name, source_url,
          world_name, server_name, description, region, country_code, country_name,
          version, status, players_current, players_max, tags_json, badges_json,
          public_connect_host, public_connect_port, password_protected,
          first_seen, last_seen, metadata_json, refresh_token, is_listed, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
        ON CONFLICT(source_id, source_world_id) DO UPDATE SET
          source_name = excluded.source_name,
          source_url = excluded.source_url,
          world_name = excluded.world_name,
          server_name = excluded.server_name,
          description = excluded.description,
          region = excluded.region,
          country_code = excluded.country_code,
          country_name = excluded.country_name,
          version = excluded.version,
          status = excluded.status,
          players_current = excluded.players_current,
          players_max = excluded.players_max,
          tags_json = excluded.tags_json,
          badges_json = excluded.badges_json,
          public_connect_host = excluded.public_connect_host,
          public_connect_port = excluded.public_connect_port,
          password_protected = excluded.password_protected,
          first_seen = MIN(public_source_worlds.first_seen, excluded.first_seen),
          last_seen = excluded.last_seen,
          metadata_json = excluded.metadata_json,
          refresh_token = excluded.refresh_token,
          is_listed = 1,
          updated_at = excluded.updated_at
      `).bind(
        record.sourceId,
        record.sourceWorldId,
        record.sourceName,
        record.sourceUrl,
        record.worldName,
        record.serverName,
        record.description,
        record.region,
        record.countryCode,
        record.countryName,
        record.version,
        record.status,
        record.playersCurrent,
        record.playersMax,
        JSON.stringify(record.tags),
        JSON.stringify(record.badges),
        record.publicConnectHost,
        record.publicConnectPort,
        record.passwordProtected ? 1 : 0,
        record.firstSeen || now,
        record.lastSeen || now,
        JSON.stringify(record.metadata),
        refreshToken,
        now,
      )
    ));
  }

  await env.DB.prepare(`
    UPDATE public_source_worlds
    SET is_listed = 0, updated_at = ?
    WHERE source_id = ? AND refresh_token <> ?
  `).bind(now, sourceId, refreshToken).run();

  await recordSourceRun(env, sourceId, true, records.length);
}

async function refreshPublicSources(env: Env): Promise<void> {
  const enabled = enabledProviders(env);
  const tasks: Array<{ id: string; load: () => Promise<SourceRecord[]> }> = [];
  if (enabled.has("shrug") || enabled.has("shrug-eos-index")) {
    tasks.push({ id: "shrug-eos-index", load: () => fetchShrugSource(env) });
  }
  if (enabled.has("lobbysup")) {
    tasks.push({ id: "lobbysup", load: () => fetchLobbySupSource(env) });
  }

  for (const task of tasks) {
    try {
      const records = await task.load();
      await saveSourceRecords(env, task.id, records);
    } catch (error) {
      await recordSourceRun(env, task.id, false, 0, error instanceof Error ? error.message : String(error));
    }
  }
}

async function publicSourcesNeedRefresh(env: Env): Promise<boolean> {
  const refreshSeconds = clampInt(env.PUBLIC_SOURCE_REFRESH_SECONDS, 300, 60, 3600);
  const enabled = enabledProviders(env);
  const wanted = [
    enabled.has("shrug") || enabled.has("shrug-eos-index") ? "shrug-eos-index" : "",
    enabled.has("lobbysup") ? "lobbysup" : "",
  ].filter(Boolean);

  if (!wanted.length) return false;

  const { results } = await env.DB.prepare(
    "SELECT source_id, last_attempt_at FROM public_source_runs"
  ).all<{ source_id: string; last_attempt_at: number }>();
  const byId = new Map((results || []).map((row) => [row.source_id, Number(row.last_attempt_at || 0)]));
  const now = Math.floor(Date.now() / 1000);
  return wanted.some((sourceId) => now - (byId.get(sourceId) || 0) >= refreshSeconds);
}

function publicSourceWorld(row: Record<string, unknown>): Record<string, any> {
  const lastSeen = Number(row.last_seen || 0);
  const age = Math.max(0, Math.floor(Date.now() / 1000) - lastSeen);
  const sourceId = cleanText(row.source_id, 80);
  const sourceWorldId = cleanText(row.source_world_id, 120);
  const host = cleanText(row.public_connect_host, 255);
  const port = row.public_connect_port ? Number(row.public_connect_port) : null;
  const metadata = parseJsonObject(row.metadata_json);
  const status = cleanText(row.status, 24) || "online";
  const countryName = cleanText(row.country_name, 80);
  const region = cleanText(row.region, 80) || countryName;

  return {
    world_id: `public-${sourceId}-${sourceWorldId}`,
    world_name: row.world_name,
    description: row.description || "Public Dragonwilds server",
    region,
    country_code: cleanText(row.country_code, 4).toUpperCase(),
    country_name: countryName,
    version: row.version || "",
    status,
    players: {
      current: Number(row.players_current || 0),
      max: Number(row.players_max || 0),
    },
    tags: parseJsonArray(row.tags_json),
    mods: [],
    rules: [],
    badges: parseJsonArray(row.badges_json),
    public_connect: host ? { host, port } : null,
    last_seen: lastSeen,
    heartbeat_age_seconds: age,
    source_name: row.source_name || sourceId,
    source_url: row.source_url || "",
    directory_source: "external-public",
    source_id: sourceId,
    source_world_id: sourceWorldId,
    is_sync_world: false,
    password_protected: Boolean(Number(row.password_protected || 0)),
    host_type: "dedicated",
    classification: {
      host_type: "dedicated",
      visibility: "public",
    },
    public_discovery: metadata,
    sources: [{
      id: sourceId,
      label: row.source_name || sourceId,
      url: row.source_url || "",
      official: false,
    }],
  };
}

function addToMultiMap<T>(map: Map<string, T[]>, key: string, value: T): void {
  if (!key) return;
  const current = map.get(key);
  if (current) current.push(value);
  else map.set(key, [value]);
}

function mergeExternalProviders(externals: Array<Record<string, any>>) {
  const endpointRows = externals.filter((world) => Boolean(endpointKey(world.public_connect?.host, world.public_connect?.port)));
  const noEndpointRows = externals.filter((world) => !endpointKey(world.public_connect?.host, world.public_connect?.port));
  const byNameBuild = new Map<string, typeof endpointRows>();
  const byName = new Map<string, typeof endpointRows>();

  for (const world of endpointRows) {
    addToMultiMap(byNameBuild, `${nameKey(world.world_name)}|${versionKey(world.version)}`, world);
    addToMultiMap(byName, nameKey(world.world_name), world);
  }

  const suppressed = new Set<string>();
  for (const world of noEndpointRows) {
    const exactBuild = versionKey(world.version)
      ? byNameBuild.get(`${nameKey(world.world_name)}|${versionKey(world.version)}`) || []
      : [];
    const nameOnly = byName.get(nameKey(world.world_name)) || [];
    const candidates = exactBuild.length === 1 ? exactBuild : (!versionKey(world.version) && nameOnly.length === 1 ? nameOnly : []);
    if (candidates.length !== 1) continue;

    const target = candidates[0];
    target.sources = [...target.sources, ...world.sources];
    target.tags = [...new Set([...target.tags, ...world.tags])].slice(0, 24);
    target.badges = [...new Set([...target.badges, ...world.badges])].slice(0, 24);
    if (!target.version && world.version) target.version = world.version;
    if ((!target.players.current && !target.players.max) && (world.players.current || world.players.max)) {
      target.players = world.players;
    }
    suppressed.add(world.world_id);
  }

  return {
    worlds: externals.filter((world) => !suppressed.has(world.world_id)),
    suppressedCount: suppressed.size,
  };
}

function matchExternalToSync(
  syncWorlds: Array<Record<string, any>>,
  externalWorlds: Array<Record<string, any>>,
) {
  const byEndpoint = new Map<string, typeof syncWorlds>();
  const byNameBuild = new Map<string, typeof syncWorlds>();

  for (const world of syncWorlds) {
    const endpoint = endpointKey(world.public_connect?.host, world.public_connect?.port);
    if (endpoint) addToMultiMap(byEndpoint, endpoint, world);
    const key = `${nameKey(world.world_name)}|${versionKey(world.version)}`;
    if (nameKey(world.world_name) && versionKey(world.version)) addToMultiMap(byNameBuild, key, world);
  }

  const suppressed = new Set<string>();
  for (const external of externalWorlds) {
    const endpoint = endpointKey(external.public_connect?.host, external.public_connect?.port);
    let candidates = endpoint ? byEndpoint.get(endpoint) || [] : [];
    let matchMethod = endpoint && candidates.length === 1 ? "endpoint" : "";

    if (candidates.length !== 1 && !endpoint && versionKey(external.version)) {
      candidates = byNameBuild.get(`${nameKey(external.world_name)}|${versionKey(external.version)}`) || [];
      if (candidates.length === 1) matchMethod = "exact-name-build";
    }

    if (candidates.length !== 1) continue;

    const sync = candidates[0];
    sync.sources = [
      ...sync.sources,
      ...external.sources.map((source: Record<string, any>) => ({ ...source, matched_by: matchMethod })),
    ];
    const syncRecord = sync as typeof sync & {
      external_observations?: Array<Record<string, unknown>>;
      country_code?: string;
      country_name?: string;
    };
    syncRecord.external_observations = [
      ...(syncRecord.external_observations || []),
      {
        source_id: external.source_id,
        source_world_id: external.source_world_id,
        matched_by: matchMethod,
        source_name: external.source_name,
        source_url: external.source_url,
      },
    ];
    if (!sync.region && external.region) sync.region = external.region;
    if (!syncRecord.country_code && external.country_code) syncRecord.country_code = external.country_code;
    if (!syncRecord.country_name && external.country_name) syncRecord.country_name = external.country_name;
    suppressed.add(external.world_id);
  }

  return {
    worlds: [
      ...syncWorlds,
      ...externalWorlds.filter((world) => !suppressed.has(world.world_id)),
    ],
    suppressedCount: suppressed.size,
  };
}

async function sourceStatus(env: Env) {
  const { results } = await env.DB.prepare(`
    SELECT source_id, last_attempt_at, last_success_at, last_error, last_count
    FROM public_source_runs
    ORDER BY source_id ASC
  `).all<Record<string, unknown>>();

  return (results || []).map((row) => ({
    source_id: row.source_id,
    last_attempt_at: Number(row.last_attempt_at || 0),
    last_success_at: Number(row.last_success_at || 0),
    last_error: row.last_error || "",
    last_count: Number(row.last_count || 0),
  }));
}

async function collectDirectoryWorlds(env: Env) {
  const offlineAfter = clampInt(env.OFFLINE_AFTER_SECONDS, 1800, 60, 86400);
  const syncResult = await env.DB.prepare(`
    SELECT * FROM worlds
    WHERE is_listed = 1
    ORDER BY last_seen DESC, world_name COLLATE NOCASE ASC
  `).all<Record<string, unknown>>();
  const syncWorlds = (syncResult.results || []).map((row) => publicWorld(row, offlineAfter));
  syncWorlds.sort((a, b) => {
    const aOnline = a.status === "online" || a.status === "starting" || a.status === "maintenance";
    const bOnline = b.status === "online" || b.status === "starting" || b.status === "maintenance";
    if (aOnline !== bOnline) return Number(bOnline) - Number(aOnline);
    const seenDiff = Number(b.last_seen || 0) - Number(a.last_seen || 0);
    if (seenDiff) return seenDiff;
    return String(a.world_name || "").localeCompare(String(b.world_name || ""));
  });

  return {
    worlds: syncWorlds,
    syncCount: syncWorlds.length,
    externalInputCount: 0,
    externalPublishedCount: 0,
    suppressedProviderDuplicates: 0,
    suppressedSyncDuplicates: 0,
  };
}

async function listWorlds(env: Env): Promise<Response> {
  const collected = await collectDirectoryWorlds(env);
  return json(
    {
      generated_at: Math.floor(Date.now() / 1000),
      worlds: collected.worlds,
      directory: {
        sync_worlds: collected.syncCount,
        external_public_records: collected.externalInputCount,
        external_public_worlds: collected.externalPublishedCount,
        suppressed_external_duplicates: collected.suppressedProviderDuplicates,
        suppressed_sync_duplicates: collected.suppressedSyncDuplicates,
        precedence: "dragonwilds-sync",
        match_policy: ["exact-endpoint", "exact-name+build-without-endpoint"],
        sources: await sourceStatus(env),
      },
    },
    200,
    { ...publicCorsHeaders(), "cache-control": "public, max-age=30" },
  );
}

async function getWorld(env: Env, worldId: string): Promise<Response> {
  const collected = await collectDirectoryWorlds(env);
  const world = collected.worlds.find((entry) => String(entry.world_id) === worldId);
  if (!world) return json({ error: "not_found" }, 404, publicCorsHeaders());
  return json(world, 200, {
    ...publicCorsHeaders(),
    "cache-control": "public, max-age=30",
  });
}

async function listSources(env: Env): Promise<Response> {
  return json({
    generated_at: Math.floor(Date.now() / 1000),
    precedence: "dragonwilds-sync",
    providers: [
      {
        id: "shrug-eos-index",
        label: "Dragonwilds EOS session mirror",
        url: SHRUG_SITE_URL,
        official: false,
      },
      {
        id: "lobbysup",
        label: "LobbySup public observations",
        url: LOBBYSUP_SITE_URL,
        official: false,
      },
    ],
    status: await sourceStatus(env),
    note: "Public providers are read-only community observations. They are not an official Jagex or Epic Online Services API.",
  }, 200, {
    ...publicCorsHeaders(),
    "cache-control": "public, max-age=60",
  });
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: publicCorsHeaders() });
    }

    if (request.method === "GET" && url.pathname === "/health") {
      const status = await sourceStatus(env);
      return json({
        ok: true,
        service: "dragonwilds-sync-directory",
        public_source_aggregation: false,
        public_sources: [],
      }, 200, publicCorsHeaders());
    }

    if (request.method === "GET" && url.pathname === "/api/v1/worlds") {
      return listWorlds(env);
    }

    if (request.method === "GET" && url.pathname === "/api/v1/sources") {
      return json({generated_at:Math.floor(Date.now()/1000),precedence:"dragonwilds-sync",providers:[{id:"dragonwilds-sync-heartbeats",label:"Dragonwilds Sync Worlds",official:true}],status:[],note:"This directory publishes only registered Dragonwilds Sync Worlds and their heartbeats."},200,{...publicCorsHeaders(),"cache-control":"public, max-age=60"});
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

  async scheduled(_controller: ScheduledController, env: Env, ctx: ExecutionContext): Promise<void> {
    // Sync Worlds arrive through signed heartbeat requests. No external
    // Dragonwilds server-roster providers are fetched by scheduled jobs.
  },
};
