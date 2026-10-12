// lib/i18n/loader.js
// English-only string loader. The UI still uses translation keys internally so labels
// remain centralized, but runtime language downloads and switching are intentionally
// not part of RSDW Sync.
const fs = require("fs");
const path = require("path");

const BASE = "en";
function englishPack() {
  try {
    const file = path.join(process.cwd(), "public", "locales", "en.json");
    const pack = JSON.parse(fs.readFileSync(file, "utf8"));
    return pack?.strings && typeof pack.strings === "object" ? pack.strings : {};
  } catch {
    return {};
  }
}

function loadResources() { return { [BASE]: { translation: englishPack() } }; }
function languageMeta() { return { code: BASE, dir: "ltr" }; }

module.exports = { BASE, loadResources, languageMeta };
