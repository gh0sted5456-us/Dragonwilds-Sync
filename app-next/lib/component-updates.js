const fs = require("fs");
const path = require("path");
const dbm = require("./db");

const NEXUS_URL = "https://www.nexusmods.com/runescapedragonwilds/mods/4?tab=files";
const RUNESCHEMA_API = "https://api.github.com/repos/gh0sted5456-us/RuneSchema/releases/latest";
const RUNESCHEMA_URL = "https://github.com/gh0sted5456-us/RuneSchema";
const CACHE_MS = 10 * 60 * 1000;
const g = globalThis;

function cleanVersion(value) {
  return String(value || "").trim().replace(/^v/i, "").replace(/[),;]+$/, "");
}
function different(installed, latest) {
  if (!installed || !latest) return false;
  return cleanVersion(installed).toLowerCase() !== cleanVersion(latest).toLowerCase();
}
function gameBin(root, platform) {
  return root
    ? path.join(root, "RSDragonwilds", "Binaries", platform === "gamepass" ? "WinGDK" : "Win64")
    : null;
}
function readLog(root, platform) {
  const bin = gameBin(root, platform);
  if (!bin) return { bin: null, ue4ssDir: null, exists: false, text: "" };
  const ue4ssDir = path.join(bin, "ue4ss");
  const log = path.join(ue4ssDir, "UE4SS.log");
  let text = "";
  try {
    if (fs.existsSync(log)) {
      const stat = fs.statSync(log);
      const max = 8 * 1024 * 1024;
      const start = Math.max(0, stat.size - max);
      const length = Math.min(max, stat.size);
      const fd = fs.openSync(log, "r");
      const buffer = Buffer.alloc(length);
      fs.readSync(fd, buffer, 0, length, start);
      fs.closeSync(fd);
      text = buffer.toString("utf8");
    }
  } catch {}
  return { bin, ue4ssDir, exists: fs.existsSync(ue4ssDir), text };
}
function localVersions(root, platform) {
  const state = readLog(root, platform);
  const ue = state.text.match(/(?:RE-)?UE4SS[^\r\n]{0,180}?(?:version\s*[:=]?\s*|\bv\s*)?(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z._-]+)?)/i)
    || state.text.match(/\b(\d+\.\d+\.\d+-g?[0-9a-f]{7,})\b/i);
  const rs = state.text.match(/RuneSchema[^\r\n]{0,180}?(?:version\s*[:=]?\s*|\bv\s*)?(\d+\.\d+\.\d+(?:\.\d+)?(?:[-+][0-9A-Za-z._-]+)?)/i);
  return {
    installed: state.exists,
    ue4ss: ue ? cleanVersion(ue[1]) : null,
    runeSchema: rs ? cleanVersion(rs[1]) : null,
  };
}

async function fetchText(url, accept = "text/html") {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 8000);
  try {
    const response = await fetch(url, {
      cache: "no-store",
      signal: controller.signal,
      headers: {
        accept,
        "user-agent": "Mozilla/5.0 RSDW-Sync/1.0 update-check",
      },
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.text();
  } finally {
    clearTimeout(timer);
  }
}

function visibleText(html) {
  return String(html || "")
    .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, " ")
    .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;|&#160;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/\s+/g, " ");
}

function versionAfterLabel(text, labels) {
  for (const label of labels) {
    const pattern = new RegExp(
      label + "[\\s\\S]{0,900}?\\bVersion\\b[\\s\\S]{0,120}?(\\d+\\.\\d+\\.\\d+(?:[-+][0-9A-Za-z._-]+)?)",
      "i"
    );
    const match = text.match(pattern);
    if (match) return cleanVersion(match[1]);
  }
  return null;
}

async function latestNexusVersions() {
  const html = await fetchText(NEXUS_URL);
  const text = visibleText(html);

  const gamepass = versionAfterLabel(text, [
    "UE4SS\\s+5\\.6\\s+Xbox",
    "UE4SS[^.]{0,80}GAMEPASS",
  ]);
  const steam = versionAfterLabel(text, [
    "UE4SS\\s+Steam\\s*\\(latest\\)",
    "UE4SS[^.]{0,80}Steam[^.]{0,40}latest",
  ]);

  const overallMatch = text.match(
    /UE4SS\s+for\s+RSDragonwilds[\s\S]{0,900}?\bVersion\b[\s\S]{0,120}?(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z._-]+)?)/i
  );
  const overall = overallMatch ? cleanVersion(overallMatch[1]) : null;

  if (!steam && !gamepass && !overall) {
    throw new Error("Nexus page did not expose UE4SS file versions");
  }
  return {
    steam: steam || overall,
    gamepass: gamepass || overall,
  };
}
async function latestRuneSchemaVersion() {
  const raw = await fetchText(RUNESCHEMA_API, "application/vnd.github+json");
  const release = JSON.parse(raw);
  const value = release.tag_name || release.name;
  if (!value) throw new Error("GitHub latest release has no version tag");
  return cleanVersion(value);
}

function maxRuneSchema(steam, gamepass) {
  // We do not rank arbitrary build suffixes. If both platforms report a version,
  // identical is enough; otherwise show the platform that actually exposed one.
  if (steam?.runeSchema && steam.runeSchema === gamepass?.runeSchema) return steam.runeSchema;
  return steam?.runeSchema || gamepass?.runeSchema || null;
}

async function getStatus({ force = false } = {}) {
  const now = Date.now();
  if (!force && g.__DWS_COMPONENT_UPDATES && now - g.__DWS_COMPONENT_UPDATES.at < CACHE_MS) {
    return g.__DWS_COMPONENT_UPDATES.value;
  }

  const steamRoot = dbm.getSetting("clientInstall:steam", null);
  const gamepassRoot = dbm.getSetting("clientInstall:gamepass", null);
  const steam = localVersions(steamRoot, "steam");
  const gamepass = localVersions(gamepassRoot, "gamepass");

  const [nexusResult, runeResult] = await Promise.allSettled([
    latestNexusVersions(),
    latestRuneSchemaVersion(),
  ]);
  const nexusLatest = nexusResult.status === "fulfilled"
    ? nexusResult.value
    : { steam: null, gamepass: null };
  const runeLatest = runeResult.status === "fulfilled" ? runeResult.value : null;
  const localRune = maxRuneSchema(steam, gamepass);

  const items = [
    {
      id: "ue4ss-steam",
      label: "UE4SS · Steam",
      platform: "Steam",
      source: "Nexus Mods",
      url: NEXUS_URL,
      installed: steam.installed,
      installedVersion: steam.ue4ss,
      latestVersion: nexusLatest.steam,
      updateAvailable: different(steam.ue4ss, nexusLatest.steam),
      error: nexusResult.status === "rejected" ? nexusResult.reason?.message || "Nexus check failed" : null,
    },
    {
      id: "ue4ss-gamepass",
      label: "UE4SS · PC Game Pass",
      platform: "PC Game Pass",
      source: "Nexus Mods",
      url: NEXUS_URL,
      installed: gamepass.installed,
      installedVersion: gamepass.ue4ss,
      latestVersion: nexusLatest.gamepass,
      updateAvailable: different(gamepass.ue4ss, nexusLatest.gamepass),
      error: nexusResult.status === "rejected" ? nexusResult.reason?.message || "Nexus check failed" : null,
    },
    {
      id: "runeschema",
      label: "RuneSchema",
      platform: "Steam / PC Game Pass",
      source: "GitHub",
      url: RUNESCHEMA_URL,
      installed: !!localRune,
      installedVersion: localRune,
      latestVersion: runeLatest,
      updateAvailable: different(localRune, runeLatest),
      error: runeResult.status === "rejected" ? runeResult.reason?.message || "GitHub check failed" : null,
    },
  ];

  const value = {
    ok: true,
    checkedAt: new Date().toISOString(),
    updateAvailable: items.some((item) => item.updateAvailable),
    items,
  };
  g.__DWS_COMPONENT_UPDATES = { at: now, value };
  return value;
}

module.exports = { getStatus, cleanVersion, different, localVersions };
