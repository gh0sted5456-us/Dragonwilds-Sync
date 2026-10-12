const dbm = require("./db");

const DEFINITIONS = {
  nexus: { setting: "nexusApiKey", env: "RSDW_NEXUS_API_KEY" },
  curseforge: { setting: "curseForgeApiKey", env: "RSDW_CURSEFORGE_API_KEY" },
};

function apiKey(provider) {
  const def = DEFINITIONS[provider];
  if (!def) return "";
  const environment = String(process.env[def.env] || "").trim();
  if (environment) return environment;
  try { return String(dbm.getSetting(def.setting, "") || "").trim(); } catch { return ""; }
}

function configured(provider) { return !!apiKey(provider); }

module.exports = { apiKey, configured };
