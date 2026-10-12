const assert = require("assert");
const fs = require("fs");
const path = require("path");
const { nexusRuneSchemaVersion, ue4ssStatus, newerVersion, localVersions, UE4SS_COMPAT_VERSION } = require("../lib/component-updates");

assert.equal(nexusRuneSchemaVersion("<h1>RuneSchema - RSDW Modding Community</h1><div>Version</div><div>0.7.7.6</div>"), "0.7.7.6");
assert.throws(() => nexusRuneSchemaVersion("Version 0.7.7.6"), /did not expose/);
assert.equal(ue4ssStatus("3.0.0", UE4SS_COMPAT_VERSION).updateAvailable, true);
assert.equal(ue4ssStatus("3.0.0", "3.1.0").updateAvailable, false, "unknown UE4SS builds must not be recommended automatically");
assert.equal(ue4ssStatus("3.0.0", "3.1.0").compatibility, "unverified");
assert.equal(newerVersion("0.7.7.9m", "0.7.7.6"), false, "older Nexus lane must not show as an update");
assert.equal(newerVersion("0.7.7.6", "0.7.7.9m"), true);
const root = fs.mkdtempSync(path.join(__dirname, ".component-lanes-"));
try {
  const log = path.join(root, "RSDragonwilds", "Binaries", "Win64", "ue4ss", "UE4SS.log");
  fs.mkdirSync(path.dirname(log), { recursive: true });
  fs.writeFileSync(log, "UE4SS version 3.0.1-gf6d5f942\nRuneSchema version 0.7.7.9m\n");
  assert.equal(localVersions(root, "steam").runeSchema, "0.7.7.9m");
} finally { fs.rmSync(root, { recursive: true, force: true }); }
console.log("Framework update lanes and compatibility gate: OK");
