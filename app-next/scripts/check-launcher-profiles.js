const assert = require("assert");
const fs = require("fs");
const os = require("os");
const path = require("path");

const sandbox = fs.mkdtempSync(path.join(os.tmpdir(), "rsdw-launcher-profiles-"));
process.env.APP_MANAGER_DATA_DIR = path.join(sandbox, "data");
const dbm = require("../lib/db");

try {
  const initial = dbm.listLauncherProfiles();
  assert.equal(initial.length, 1, "a fresh install should receive one player profile");
  assert.equal(dbm.getActiveLauncherProfileId(), initial[0].profile_id);

  dbm.upsertProfile({ profile_id: "joined-one", display_name: "Friend World", connection: {} });
  assert.deepEqual(dbm.listLauncherProfileWorldIds(initial[0].profile_id, "player"), ["joined-one"]);

  const second = dbm.upsertLauncherProfile({
    profile_id: "profile-two",
    display_name: "Co-op Crew",
    links: { steam: "https://steamcommunity.com/id/example" },
  });
  dbm.setActiveLauncherProfile(second.profile_id);
  dbm.upsertProfile({ profile_id: "joined-two", display_name: "Other World", connection: {} });
  assert.deepEqual(dbm.listLauncherProfileWorldIds(second.profile_id, "player"), ["joined-two"]);
  assert.deepEqual(dbm.listLauncherProfileWorldIds(initial[0].profile_id, "player"), ["joined-one"]);

  const removed = dbm.deleteLauncherProfile(second.profile_id);
  assert.equal(removed.changes, 1);
  assert.equal(dbm.getActiveLauncherProfileId(), initial[0].profile_id);
  assert.deepEqual(dbm.listLauncherProfileWorldIds(initial[0].profile_id, "player"), ["joined-one", "joined-two"]);
  assert.equal(dbm.deleteLauncherProfile(initial[0].profile_id).reason, "last-profile");

  dbm.setSetting("serverModeEnabled", true);
  assert.equal(dbm.getSetting("serverModeEnabled", false), true);
  console.log("Launcher profiles: OK");
} finally {
  try { dbm.db().close(); } catch {}
  fs.rmSync(sandbox, { recursive: true, force: true });
}
