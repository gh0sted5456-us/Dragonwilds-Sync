type ScanEnv = {
  DB: D1Database;
  PUBLIC_SOURCE_PROVIDERS?: string;
  PUBLIC_SOURCE_TIMEOUT_MS?: string;
  PUBLIC_SOURCE_BATCH_PAGES?: string;
};

type PublicRecord = {
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
  host: string;
  port: number | null;
  passwordProtected: boolean;
  firstSeen: number;
  lastSeen: number;
  metadata: Record<string, unknown>;
};

type ScanState = {
  source_id: string;
  last_attempt_at: number;
  last_success_at: number;
  last_error: string;
  last_count: number;
  scan_cursor: number;
  scan_generation: string;
  scan_started_at: number;
  scan_completed_at: number;
  scan_total: number;
};

const SHRUG_API_URL = 'https://shrug.games/api/rsdw/servers';
const SHRUG_SITE_URL = 'https://shrug.games/games/runescape-dragonwilds/servers/';
const LOBBYSUP_API_URL = 'https://www.lobbysup.com/api/servers/dragonwilds';
const LOBBYSUP_SITE_URL = 'https://www.lobbysup.com/dragonwilds';
const MIN_SCAN_INTERVAL_SECONDS = 240;

const clampInt = (value: unknown, fallback: number, min: number, max: number): number => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.min(max, Math.max(min, Math.trunc(parsed))) : fallback;
};
const cleanText = (value: unknown, max = 160): string => typeof value === 'string' ? value.trim().slice(0, max) : '';
const normalizeHost = (value: unknown): string => cleanText(value, 255).toLowerCase().replace(/^\[|\]$/g, '').replace(/\.$/, '');

function stableHash(value: string): string {
  let a = 0x811c9dc5;
  let b = 0x9e3779b9;
  for (let i = 0; i < value.length; i += 1) {
    const code = value.charCodeAt(i);
    a = Math.imul(a ^ code, 0x01000193);
    b = Math.imul(b ^ (code + i), 0x85ebca6b);
  }
  return `${(a >>> 0).toString(16).padStart(8, '0')}${(b >>> 0).toString(16).padStart(8, '0')}`;
}

function decodeHtml(value: string): string {
  return value
    .replace(/<br\s*\/?>/gi, ' ')
    .replace(/<[^>]*>/g, ' ')
    .replace(/&nbsp;|&#160;/gi, ' ')
    .replace(/&amp;/gi, '&')
    .replace(/&quot;|&#34;/gi, '"')
    .replace(/&#39;|&apos;/gi, "'")
    .replace(/&lt;/gi, '<')
    .replace(/&gt;/gi, '>')
    .replace(/\s+/g, ' ')
    .trim();
}

function extractClassText(fragment: string, className: string): string {
  const escaped = className.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const pattern = new RegExp(`<[^>]*class=["'][^"']*\\b${escaped}\\b[^"']*["'][^>]*>([\\s\\S]*?)<\\/[^>]+>`, 'i');
  return decodeHtml(pattern.exec(fragment)?.[1] || '');
}

function extractDifficulty(fragment: string): string {
  const match = /<[^>]*class=["'][^"']*\bsb-badge--diff-[^"']*["'][^>]*>([\s\S]*?)<\/[^>]+>/i.exec(fragment);
  return decodeHtml(match?.[1] || '');
}

function hasClass(fragment: string, className: string): boolean {
  const escaped = className.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return new RegExp(`class=["'][^"']*\\b${escaped}\\b[^"']*["']`, 'i').test(fragment);
}

function parseShrugRows(payload: string): Array<Record<string, unknown>> {
  const chunks = payload.split(/<div\b[^>]*class=["'][^"']*\bsb-row\b[^"']*["'][^>]*>/gi).slice(1);
  const rows: Array<Record<string, unknown>> = [];
  for (const fragment of chunks) {
    const serverName = extractClassText(fragment, 'sb-server-name');
    const worldName = extractClassText(fragment, 'sb-world-name');
    if (!serverName && !worldName) continue;
    const playerText = extractClassText(fragment, 'sb-player-count');
    const playerMatch = /(\d+)\s*\/\s*(\d+)/.exec(playerText);
    rows.push({
      serverName,
      worldName,
      difficulty: extractDifficulty(fragment),
      pvp: hasClass(fragment, 'sb-badge--pvp'),
      locked: hasClass(fragment, 'sb-badge--locked'),
      players: playerMatch ? Number(playerMatch[1]) : 0,
      maxPlayers: playerMatch ? Number(playerMatch[2]) : 0,
      build: extractClassText(fragment, 'sb-row-build').replace(/^CL-/i, ''),
    });
  }
  return rows;
}

function parseAddress(value: unknown): { host: string; port: number } {
  const address = cleanText(value, 320);
  if (!address) return { host: '', port: 7777 };
  if (address.startsWith('[')) {
    const match = /^\[([^\]]+)\](?::(\d+))?$/.exec(address);
    return { host: normalizeHost(match?.[1] || address), port: clampInt(match?.[2], 7777, 1, 65535) };
  }
  const colon = address.lastIndexOf(':');
  if (colon > 0 && address.indexOf(':') === colon) {
    return { host: normalizeHost(address.slice(0, colon)), port: clampInt(address.slice(colon + 1), 7777, 1, 65535) };
  }
  return { host: normalizeHost(address), port: 7777 };
}

function parseRemoteTimestamp(value: unknown, fallback: number): number {
  if (typeof value === 'number' && Number.isFinite(value)) return value > 1e12 ? Math.floor(value / 1000) : Math.floor(value);
  const parsed = Date.parse(String(value || ''));
  return Number.isFinite(parsed) ? Math.floor(parsed / 1000) : fallback;
}

async function fetchWithTimeout(url: string, timeoutMs: number, accept: string): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { headers: { Accept: accept, 'User-Agent': 'DragonwildsSync-Directory/2.0' }, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

function normalizeShrugRows(rows: Array<Record<string, unknown>>, now: number): PublicRecord[] {
  const records: PublicRecord[] = [];
  const seen = new Set<string>();
  for (const row of rows) {
    const serverName = cleanText(row.serverName, 100);
    const worldName = cleanText(row.worldName || row.serverName, 100) || 'Dragonwilds World';
    const build = cleanText(row.build, 64).replace(/^CL-/i, '');
    const sourceWorldId = stableHash(`${serverName.toLocaleLowerCase('en-US')}|${worldName.toLocaleLowerCase('en-US')}|${build}`);
    if (seen.has(sourceWorldId)) continue;
    seen.add(sourceWorldId);
    const difficulty = cleanText(row.difficulty, 40);
    const tags = ['DEDICATED', 'EOS', ...(difficulty ? [difficulty.toUpperCase()] : [])];
    if (row.pvp) tags.push('PVP');
    if (row.locked) tags.push('PASSWORD');
    records.push({
      sourceId: 'shrug-eos-index', sourceWorldId,
      sourceName: 'Dragonwilds EOS session mirror', sourceUrl: SHRUG_SITE_URL,
      worldName, serverName,
      description: `Public Dragonwilds session${build ? ` · CL-${build}` : ''}`,
      region: '', countryCode: '', countryName: '', version: build ? `CL-${build}` : '', status: 'online',
      playersCurrent: clampInt(row.players, 0, 0, 10000), playersMax: clampInt(row.maxPlayers, 0, 0, 10000),
      tags, badges: [], host: '', port: null, passwordProtected: Boolean(row.locked),
      firstSeen: now, lastSeen: now,
      metadata: { provider: 'shrug-eos-index', server_name: serverName, build, route_available: false },
    });
  }
  return records;
}

function normalizeLobbySupRows(rows: Array<Record<string, unknown>>, now: number): PublicRecord[] {
  const records: PublicRecord[] = [];
  const seen = new Set<string>();
  for (const row of rows) {
    const { host, port } = parseAddress(row.address);
    const worldName = cleanText(row.name, 100) || 'Dragonwilds World';
    const sourceWorldId = stableHash(`${worldName.toLocaleLowerCase('en-US')}|${normalizeHost(host)}|${port}`);
    if (seen.has(sourceWorldId)) continue;
    seen.add(sourceWorldId);
    const countryCode = cleanText(row.countryCode, 2).toUpperCase();
    const countryName = cleanText(row.country, 80);
    const online = row.online === undefined ? true : Boolean(row.online);
    records.push({
      sourceId: 'lobbysup', sourceWorldId,
      sourceName: 'LobbySup public observations', sourceUrl: LOBBYSUP_SITE_URL,
      worldName, serverName: worldName,
      description: 'Public Dragonwilds server observed by LobbySup',
      region: countryName, countryCode, countryName,
      version: cleanText(row.version ?? row.build, 64), status: online ? 'online' : 'offline',
      playersCurrent: clampInt(row.players, 0, 0, 10000), playersMax: clampInt(row.maxPlayers, 0, 0, 10000),
      tags: ['DRAGONWILDS', 'PUBLIC'], badges: [], host, port, passwordProtected: Boolean(row.passwordProtected ?? row.locked),
      firstSeen: parseRemoteTimestamp(row.firstSeen, now), lastSeen: parseRemoteTimestamp(row.lastSeen ?? row.lastUpdated, now),
      metadata: { provider: 'lobbysup', address: cleanText(row.address, 320), map: cleanText(row.map, 100), latitude: row.lat ?? null, longitude: row.lon ?? null },
    });
  }
  return records;
}

async function getScanState(env: ScanEnv, sourceId: string): Promise<ScanState> {
  const row = await env.DB.prepare('SELECT * FROM public_source_runs WHERE source_id = ?').bind(sourceId).first<ScanState>();
  return row || {
    source_id: sourceId, last_attempt_at: 0, last_success_at: 0, last_error: '', last_count: 0,
    scan_cursor: 0, scan_generation: '', scan_started_at: 0, scan_completed_at: 0, scan_total: 0,
  };
}

async function markAttempt(env: ScanEnv, sourceId: string, state: ScanState, now: number): Promise<void> {
  await env.DB.prepare(`
    INSERT INTO public_source_runs
      (source_id,last_attempt_at,last_success_at,last_error,last_count,scan_cursor,scan_generation,scan_started_at,scan_completed_at,scan_total)
    VALUES (?,?,?,?,?,?,?,?,?,?)
    ON CONFLICT(source_id) DO UPDATE SET last_attempt_at=excluded.last_attempt_at
  `).bind(sourceId, now, state.last_success_at || 0, state.last_error || '', state.last_count || 0,
    state.scan_cursor || 0, state.scan_generation || '', state.scan_started_at || 0, state.scan_completed_at || 0, state.scan_total || 0).run();
}

async function saveRecords(env: ScanEnv, records: PublicRecord[], generation: string, now: number): Promise<void> {
  for (let offset = 0; offset < records.length; offset += 50) {
    const chunk = records.slice(offset, offset + 50);
    await env.DB.batch(chunk.map((record) => env.DB.prepare(`
      INSERT INTO public_source_worlds (
        source_id,source_world_id,source_name,source_url,world_name,server_name,description,region,country_code,country_name,
        version,status,players_current,players_max,tags_json,badges_json,public_connect_host,public_connect_port,password_protected,
        first_seen,last_seen,metadata_json,refresh_token,is_listed,updated_at
      ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?)
      ON CONFLICT(source_id,source_world_id) DO UPDATE SET
        source_name=excluded.source_name,source_url=excluded.source_url,world_name=excluded.world_name,server_name=excluded.server_name,
        description=excluded.description,region=excluded.region,country_code=excluded.country_code,country_name=excluded.country_name,
        version=excluded.version,status=excluded.status,players_current=excluded.players_current,players_max=excluded.players_max,
        tags_json=excluded.tags_json,badges_json=excluded.badges_json,public_connect_host=excluded.public_connect_host,
        public_connect_port=excluded.public_connect_port,password_protected=excluded.password_protected,
        first_seen=MIN(public_source_worlds.first_seen,excluded.first_seen),last_seen=excluded.last_seen,metadata_json=excluded.metadata_json,
        refresh_token=excluded.refresh_token,is_listed=1,updated_at=excluded.updated_at
    `).bind(
      record.sourceId, record.sourceWorldId, record.sourceName, record.sourceUrl, record.worldName, record.serverName,
      record.description, record.region, record.countryCode, record.countryName, record.version, record.status,
      record.playersCurrent, record.playersMax, JSON.stringify(record.tags), JSON.stringify(record.badges), record.host, record.port,
      record.passwordProtected ? 1 : 0, record.firstSeen || now, record.lastSeen || now, JSON.stringify(record.metadata), generation, now,
    )));
  }
}

async function listedCount(env: ScanEnv, sourceId: string): Promise<number> {
  const row = await env.DB.prepare('SELECT COUNT(*) AS count FROM public_source_worlds WHERE source_id = ? AND is_listed = 1')
    .bind(sourceId).first<{ count: number }>();
  return Number(row?.count || 0);
}

async function recordFailure(env: ScanEnv, sourceId: string, error: unknown, now: number): Promise<void> {
  await env.DB.prepare(`UPDATE public_source_runs SET last_attempt_at=?, last_error=? WHERE source_id=?`)
    .bind(now, cleanText(error instanceof Error ? error.message : String(error), 500), sourceId).run();
}

async function scanLobbySup(env: ScanEnv, force: boolean): Promise<void> {
  const sourceId = 'lobbysup';
  const now = Math.floor(Date.now() / 1000);
  const state = await getScanState(env, sourceId);
  if (!force && now - Number(state.last_attempt_at || 0) < MIN_SCAN_INTERVAL_SECONDS) return;
  await markAttempt(env, sourceId, state, now);
  try {
    const timeoutMs = clampInt(env.PUBLIC_SOURCE_TIMEOUT_MS, 5000, 1000, 15000);
    const response = await fetchWithTimeout(LOBBYSUP_API_URL, timeoutMs, 'application/json');
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload: unknown = await response.json();
    const raw = payload && typeof payload === 'object' && !Array.isArray(payload) ? (payload as Record<string, unknown>).servers : payload;
    const rows = Array.isArray(raw) ? raw.filter((row): row is Record<string, unknown> => Boolean(row && typeof row === 'object' && !Array.isArray(row))) : [];
    if (!rows.length) throw new Error('LobbySup returned no usable rows');
    const generation = crypto.randomUUID();
    const records = normalizeLobbySupRows(rows, now);
    await saveRecords(env, records, generation, now);
    await env.DB.prepare('UPDATE public_source_worlds SET is_listed=0, updated_at=? WHERE source_id=? AND refresh_token<>?')
      .bind(now, sourceId, generation).run();
    const total = await listedCount(env, sourceId);
    await env.DB.prepare(`UPDATE public_source_runs SET last_attempt_at=?,last_success_at=?,last_error='',last_count=?,scan_cursor=0,scan_generation='',scan_started_at=?,scan_completed_at=?,scan_total=? WHERE source_id=?`)
      .bind(now, now, total, now, now, total, sourceId).run();
  } catch (error) {
    await recordFailure(env, sourceId, error, now);
  }
}

async function scanShrug(env: ScanEnv, force: boolean): Promise<void> {
  const sourceId = 'shrug-eos-index';
  const now = Math.floor(Date.now() / 1000);
  const state = await getScanState(env, sourceId);
  if (!force && now - Number(state.last_attempt_at || 0) < MIN_SCAN_INTERVAL_SECONDS) return;
  await markAttempt(env, sourceId, state, now);

  let generation = cleanText(state.scan_generation, 80);
  let cursor = clampInt(state.scan_cursor, 0, 0, 1000000);
  let startedAt = Number(state.scan_started_at || 0);
  if (!generation || cursor === 0) {
    generation = crypto.randomUUID();
    cursor = 0;
    startedAt = now;
  }

  try {
    const timeoutMs = clampInt(env.PUBLIC_SOURCE_TIMEOUT_MS, 5000, 1000, 15000);
    const batchPages = clampInt(env.PUBLIC_SOURCE_BATCH_PAGES, 35, 5, 45);
    const offsets = Array.from({ length: batchPages }, (_, index) => cursor + index * 10);
    const pages = await Promise.allSettled(offsets.map(async (offset) => {
      const response = await fetchWithTimeout(`${SHRUG_API_URL}?offset=${offset}&sort=players`, timeoutMs, 'text/html');
      if (!response.ok) throw new Error(`offset ${offset}: HTTP ${response.status}`);
      return { offset, rows: parseShrugRows(await response.text()) };
    }));

    const successful = pages
      .filter((page): page is PromiseFulfilledResult<{ offset: number; rows: Array<Record<string, unknown>> }> => page.status === 'fulfilled')
      .map((page) => page.value)
      .sort((a, b) => a.offset - b.offset);
    if (!successful.length) throw new Error('Shrug EOS mirror returned no successful pages');

    const records = normalizeShrugRows(successful.flatMap((page) => page.rows), now);
    if (records.length) await saveRecords(env, records, generation, now);

    const terminal = successful.find((page) => page.rows.length < 10);
    const nextCursor = terminal ? 0 : cursor + batchPages * 10;
    if (terminal) {
      await env.DB.prepare('UPDATE public_source_worlds SET is_listed=0, updated_at=? WHERE source_id=? AND refresh_token<>?')
        .bind(now, sourceId, generation).run();
    }
    const total = await listedCount(env, sourceId);
    await env.DB.prepare(`
      UPDATE public_source_runs SET
        last_attempt_at=?,last_success_at=?,last_error='',last_count=?,scan_cursor=?,scan_generation=?,scan_started_at=?,scan_completed_at=?,scan_total=?
      WHERE source_id=?
    `).bind(now, now, total, nextCursor, terminal ? '' : generation, startedAt, terminal ? now : Number(state.scan_completed_at || 0), total, sourceId).run();
  } catch (error) {
    await recordFailure(env, sourceId, error, now);
  }
}

function enabledProviders(env: ScanEnv): Set<string> {
  const values = cleanText(env.PUBLIC_SOURCE_PROVIDERS || 'shrug,lobbysup', 200).split(',').map((value) => value.trim().toLowerCase()).filter(Boolean);
  return new Set(values);
}

export async function scanPublicSourcesIncrementally(env: ScanEnv, force = false): Promise<void> {
  const enabled = enabledProviders(env);
  const tasks: Promise<void>[] = [];
  if (enabled.has('lobbysup')) tasks.push(scanLobbySup(env, force));
  if (enabled.has('shrug') || enabled.has('shrug-eos-index')) tasks.push(scanShrug(env, force));
  await Promise.all(tasks);
}
