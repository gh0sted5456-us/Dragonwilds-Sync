const NEXUS_GAME = "runescapedragonwilds";

function normalizeProvider(identity = {}) {
  const provider = String(identity.provider || "").toLowerCase();
  if (["nexus", "curseforge"].includes(provider)) return provider;
  try {
    const host = new URL(identity.projectUrl).hostname.toLowerCase();
    if (host === "nexusmods.com" || host.endsWith(".nexusmods.com")) return "nexus";
    if (host === "curseforge.com" || host.endsWith(".curseforge.com")) return "curseforge";
  } catch {}
  return null;
}

function compareVersions(installed, latest) {
  const parts = (value) => String(value || "").replace(/^v/i, "").split(/[.+_-]/).map((part) => /^\d+$/.test(part) ? Number(part) : part.toLowerCase());
  const a = parts(installed), b = parts(latest);
  for (let index = 0; index < Math.max(a.length, b.length); index += 1) {
    const left = a[index] ?? 0, right = b[index] ?? 0;
    if (left === right) continue;
    if (typeof left === "number" && typeof right === "number") return left < right ? -1 : 1;
    return String(left).localeCompare(String(right), undefined, { numeric: true, sensitivity: "base" });
  }
  return 0;
}

function result(identity, provider, latest = null) {
  const installedVersion = identity.version || null;
  const installedFileId = identity.fileId || null;
  const latestVersion = latest?.version || null;
  const latestFileId = latest?.fileId != null ? String(latest.fileId) : null;
  const updateAvailable = !!latest && (
    (installedFileId && latestFileId && installedFileId !== latestFileId)
    || (installedVersion && latestVersion && compareVersions(installedVersion, latestVersion) < 0)
  );
  return {
    provider,
    projectUrl: identity.projectUrl || latest?.projectUrl || null,
    installedVersion,
    installedFileId,
    latestVersion,
    latestFileId,
    updateAvailable,
    checked: !!latest,
  };
}

async function checkNexus(identity, fetchImpl) {
  const apiKey = require("./provider-credentials").apiKey("nexus");
  if (!apiKey) return { ...result(identity, "nexus"), reason: "Open Nexus Mods to sign in and check this project, or set RSDW_NEXUS_API_KEY for automatic checks." };
  const projectId = String(identity.projectId || "").trim();
  if (!/^\d+$/.test(projectId)) return { ...result(identity, "nexus"), reason: "Add the numeric ProjectID to ID.txt to check Nexus Mods automatically." };
  const response = await fetchImpl(`https://api.nexusmods.com/v1/games/${NEXUS_GAME}/mods/${projectId}/files.json`, {
    headers: { apikey: apiKey, "Application-Name": "RSDW-Sync", "Application-Version": "0.1.1" },
    signal: AbortSignal.timeout(12000),
  });
  if (!response.ok) throw new Error(`Nexus Mods returned HTTP ${response.status}`);
  const payload = await response.json();
  const files = Array.isArray(payload?.files) ? payload.files.filter((file) => file?.category_id !== 6) : [];
  files.sort((a, b) => new Date(b.uploaded_time || 0) - new Date(a.uploaded_time || 0));
  const latest = files[0];
  if (!latest) return { ...result(identity, "nexus"), reason: "Nexus Mods did not return a downloadable file for this project." };
  return result(identity, "nexus", { version: latest.version || latest.name, fileId: latest.file_id, projectUrl: identity.projectUrl });
}

async function checkCurseForge(identity, fetchImpl) {
  const apiKey = require("./provider-credentials").apiKey("curseforge");
  if (!apiKey) return { ...result(identity, "curseforge"), reason: "Open CurseForge to sign in and check this project, or set RSDW_CURSEFORGE_API_KEY for automatic checks." };
  const projectId = String(identity.projectId || "").trim();
  if (!/^\d+$/.test(projectId)) return { ...result(identity, "curseforge"), reason: "Add the numeric ProjectID to ID.txt to check CurseForge automatically." };
  const response = await fetchImpl(`https://api.curseforge.com/v1/mods/${projectId}/files?pageSize=50`, {
    headers: { "x-api-key": apiKey, Accept: "application/json" },
    signal: AbortSignal.timeout(12000),
  });
  if (!response.ok) throw new Error(`CurseForge returned HTTP ${response.status}`);
  const payload = await response.json();
  const files = Array.isArray(payload?.data) ? payload.data : [];
  files.sort((a, b) => new Date(b.fileDate || 0) - new Date(a.fileDate || 0));
  const latest = files[0];
  if (!latest) return { ...result(identity, "curseforge"), reason: "CurseForge did not return a downloadable file for this project." };
  return result(identity, "curseforge", { version: latest.displayName || latest.fileName, fileId: latest.id, projectUrl: identity.projectUrl });
}

async function checkMod(identity, fetchImpl = fetch) {
  const provider = normalizeProvider(identity);
  if (!provider || !identity?.projectUrl) return { ...result(identity || {}, provider), reason: "Add Provider, ProjectURL, Version, and ProjectID to this mod's ID.txt." };
  try {
    return provider === "nexus" ? await checkNexus(identity, fetchImpl) : await checkCurseForge(identity, fetchImpl);
  } catch (error) {
    return { ...result(identity, provider), reason: error.message };
  }
}

module.exports = { normalizeProvider, compareVersions, checkMod };
