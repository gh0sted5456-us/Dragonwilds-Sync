const net = require("net");
const dbm = require("../db");

const SCHEMA = "RSDWSync.CloudManifest.v1";
const MODES = new Set(["local", "cloud", "hybrid"]);
const HOST_TYPES = {
  local: { id: "local", label: "This computer" },
  remote: { id: "remote", label: "Remote machine / VPS" },
  managed: { id: "managed", label: "Managed game-server host" },
};
const PROVIDERS = {
  google: { id: "google", label: "Google Drive", hosts: ["drive.google.com", "drive.usercontent.google.com", "googleusercontent.com"] },
  onedrive: { id: "onedrive", label: "Microsoft OneDrive", hosts: ["1drv.ms", "onedrive.live.com", "sharepoint.com", "1drv.com"] },
  dropbox: { id: "dropbox", label: "Dropbox", hosts: ["dropbox.com", "dropboxusercontent.com"] },
  generic: { id: "generic", label: "HTTPS host", hosts: [] },
};
const MAX_MANIFEST_BYTES = 4 * 1024 * 1024;
const MAX_FILES = 50000;
const configKey = (worldId) => `syncStorage:${worldId}`;

function safeHost(hostname) {
  const host = String(hostname || "").toLowerCase().replace(/^\[|\]$/g, "");
  if (!host || host === "localhost" || host.endsWith(".localhost") || host.endsWith(".local")) return false;
  const family = net.isIP(host);
  if (!family) return true;
  if (family === 4) {
    const p = host.split(".").map(Number);
    return !(p[0] === 10 || p[0] === 127 || p[0] === 0 || (p[0] === 169 && p[1] === 254) || (p[0] === 172 && p[1] >= 16 && p[1] <= 31) || (p[0] === 192 && p[1] === 168));
  }
  return host !== "::1" && !host.startsWith("fc") && !host.startsWith("fd") && !host.startsWith("fe80:");
}

function providerHostAllowed(provider, hostname) {
  if (provider === "generic") return safeHost(hostname);
  return (PROVIDERS[provider]?.hosts || []).some((suffix) => hostname === suffix || hostname.endsWith(`.${suffix}`));
}

function normalizePublicUrl(value, provider = "generic") {
  let url;
  try { url = new URL(String(value || "").trim()); }
  catch { throw new Error("Enter a valid public HTTPS link"); }
  if (url.protocol !== "https:" || url.username || url.password) throw new Error("Cloud links must use HTTPS and cannot contain credentials");
  const chosen = PROVIDERS[provider] ? provider : "generic";
  if (!safeHost(url.hostname) || !providerHostAllowed(chosen, url.hostname.toLowerCase())) throw new Error(`That link is not a supported ${PROVIDERS[chosen].label} public host`);

  if (chosen === "google") {
    const fileMatch = url.pathname.match(/\/file\/d\/([^/]+)/);
    const id = fileMatch?.[1] || url.searchParams.get("id");
    if (id) return `https://drive.usercontent.google.com/download?id=${encodeURIComponent(id)}&export=download&confirm=t`;
  }
  if (chosen === "dropbox") url.searchParams.set("dl", "1");
  if (chosen === "onedrive") url.searchParams.set("download", "1");
  return url.toString();
}

function normalizeConfig(input = {}, previous = {}) {
  const mode = MODES.has(input.mode) ? input.mode : (MODES.has(previous.mode) ? previous.mode : "local");
  const hostType = HOST_TYPES[input.hostType] ? input.hostType : (HOST_TYPES[previous.hostType] ? previous.hostType : "local");
  const provider = PROVIDERS[input.provider] ? input.provider : (PROVIDERS[previous.provider] ? previous.provider : "generic");
  const supplied = String(input.manifestUrl || "").trim();
  const providerChanged = !!previous.provider && provider !== previous.provider;
  const manifestUrl = supplied ? normalizePublicUrl(supplied, provider) : (providerChanged ? "" : String(previous.manifestUrl || ""));
  if (mode !== "local" && !manifestUrl) throw new Error("Cloud and Hybrid delivery need a public cloud manifest link");
  return { mode, hostType, provider, manifestUrl, cache: previous.cache || null };
}

function getConfig(worldId) {
  const saved = dbm.getSetting(configKey(worldId), null);
  return normalizeConfig({ mode: saved?.mode || "local", hostType: saved?.hostType || "local", provider: saved?.provider || "generic" }, saved || {});
}

function publicStatus(worldId) {
  const config = getConfig(worldId);
  return {
    mode: config.mode,
    hostType: config.hostType,
    hostTypeLabel: HOST_TYPES[config.hostType].label,
    provider: config.provider,
    providerLabel: PROVIDERS[config.provider].label,
    hasManifestUrl: !!config.manifestUrl,
    syncedAt: config.cache?.syncedAt || null,
    revision: config.cache?.revision || null,
    fileCount: config.cache?.files?.length || 0,
    lastError: config.cache?.lastError || null,
    schema: SCHEMA,
  };
}

function validateCloudManifest(payload, localManifest, provider) {
  if (!payload || payload.schema !== SCHEMA || !Array.isArray(payload.files)) throw new Error(`Cloud manifest must use schema ${SCHEMA}`);
  if (payload.files.length > MAX_FILES) throw new Error("Cloud manifest contains too many files");
  const localFiles = new Map((localManifest?.units || []).flatMap((unit) => unit.files || []).map((file) => [String(file.target), file]));
  const seen = new Set();
  const files = payload.files.map((entry) => {
    const target = String(entry.target || "").replace(/\\/g, "/");
    if (!target.startsWith("RSDragonwilds/") || target.split("/").some((part) => !part || part === "." || part === "..") || seen.has(target.toLowerCase())) throw new Error("Cloud manifest contains an unsafe or duplicate target");
    seen.add(target.toLowerCase());
    const local = localFiles.get(target);
    if (!local) throw new Error(`Cloud manifest contains a file that is not selected for this World: ${target}`);
    const size = Number(entry.size);
    const sha256 = String(entry.sha256 || "").toLowerCase();
    if (size !== Number(local.size) || sha256 !== String(local.sha256).toLowerCase()) throw new Error(`Cloud metadata does not match the local managed file: ${target}`);
    return { target, size, sha256, url: normalizePublicUrl(entry.url, provider) };
  });
  if (files.length !== localFiles.size) throw new Error(`Cloud manifest declares ${files.length} of ${localFiles.size} required files`);
  return { revision: String(payload.revision || localManifest.revision || ""), files };
}

async function fetchPublicManifest(worldId, fetchImpl = fetch) {
  const config = getConfig(worldId);
  if (!config.manifestUrl) throw new Error("No public cloud manifest link is configured");
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 20000);
  try {
    const response = await fetchImpl(config.manifestUrl, { cache: "no-store", redirect: "follow", signal: controller.signal, headers: { Accept: "application/json", "User-Agent": "RSDW-Sync/0.1" } });
    if (!response.ok) throw new Error(`Cloud manifest request failed (${response.status})`);
    const declaredLength = Number(response.headers?.get?.("content-length") || 0);
    if (declaredLength > MAX_MANIFEST_BYTES) throw new Error("Cloud manifest exceeds 4 MiB");
    const text = await response.text();
    if (Buffer.byteLength(text) > MAX_MANIFEST_BYTES) throw new Error("Cloud manifest exceeds 4 MiB");
    try { return JSON.parse(text); } catch { throw new Error("Cloud manifest is not valid JSON"); }
  } finally { clearTimeout(timeout); }
}

async function refresh(worldId, localManifest, fetchImpl = fetch) {
  const config = getConfig(worldId);
  if (config.mode === "local") return publicStatus(worldId);
  try {
    const payload = await fetchPublicManifest(worldId, fetchImpl);
    const validated = validateCloudManifest(payload, localManifest, config.provider);
    config.cache = { ...validated, syncedAt: Date.now(), lastError: null };
    dbm.setSetting(configKey(worldId), config);
    return publicStatus(worldId);
  } catch (error) {
    config.cache = { ...(config.cache || {}), lastError: String(error.message || "Cloud manifest refresh failed").replace(/https?:\/\/\S+/gi, "[redacted]") };
    dbm.setSetting(configKey(worldId), config);
    throw new Error(config.cache.lastError);
  }
}

function save(worldId, input = {}) {
  const previous = getConfig(worldId);
  const config = normalizeConfig(input, previous);
  if (input.manifestUrl || input.provider !== previous.provider) config.cache = null;
  dbm.setSetting(configKey(worldId), config);
  return publicStatus(worldId);
}

function resolveRemoteFile(worldId, file) {
  const config = getConfig(worldId);
  if (config.mode === "local") return { mode: "local", provider: config.provider, url: null };
  const match = config.cache?.files?.find((entry) => entry.target === file.target && Number(entry.size) === Number(file.size) && entry.sha256 === file.sha256);
  if (!match) {
    if (config.mode === "hybrid") return { mode: "hybrid", provider: config.provider, url: null };
    throw new Error("Cloud source is not ready for this file; refresh its manifest from Managed Mods");
  }
  return { mode: config.mode, provider: config.provider, url: match.url };
}

module.exports = { SCHEMA, PROVIDERS, HOST_TYPES, normalizePublicUrl, validateCloudManifest, fetchPublicManifest, getConfig, publicStatus, save, refresh, resolveRemoteFile };
