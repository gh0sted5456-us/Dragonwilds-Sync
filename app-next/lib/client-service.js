const dbm = require("./db");
const steamlib = require("./steamlibrary");

function parseConnection(profile) {
  try { return JSON.parse(profile?.connection_json || "{}"); }
  catch { return {}; }
}

function legacyService(connection = {}) {
  if (["steam", "epic", "gamepass"].includes(connection.service)) return connection.service;
  return connection.platform === "gamepass" ? "gamepass" : "steam";
}

function resolveProfileService(profile, options = {}) {
  if (!profile) return { profile: null, installation: null };
  const connection = parseConnection(profile);
  const hasExplicitOverride = ["service", "installDir", "executablePath", "savePath"].some((key) => Object.prototype.hasOwnProperty.call(options, key));
  if (!hasExplicitOverride && ["steam", "epic", "gamepass"].includes(connection.service) && profile.client_install && connection.serviceDetection) {
    return { profile, installation: null, connection };
  }
  const preferred = options.service || legacyService(connection);
  const installDir = options.installDir ?? profile.client_install ?? dbm.getSetting(`clientInstall:${preferred}`, null);
  const installation = steamlib.resolveClientInstallation(installDir || options.executablePath || connection.executablePath, {
    executablePath: options.executablePath ?? connection.executablePath,
    savePath: options.savePath ?? connection.savePath,
    preferred,
  });
  if (!installation) return { profile, installation: null };
  const nextConnection = {
    ...connection,
    service: installation.service,
    platform: installation.modPlatform,
    executablePath: installation.executablePath || null,
    savePath: installation.savePath || null,
    serviceDetection: {
      confidence: installation.confidence,
      reasons: installation.reasons,
      detectedAt: Date.now(),
    },
  };
  if (options.persist === false) return { profile, installation, connection: nextConnection };
  const updated = dbm.upsertProfile({
    profile_id: profile.profile_id,
    client_install: installation.installDir || profile.client_install || null,
    connection: nextConnection,
  });
  return { profile: updated, installation, connection: nextConnection };
}

module.exports = { legacyService, parseConnection, resolveProfileService };
