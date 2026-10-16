const assert = require("assert");
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const read = (relative) => fs.readFileSync(path.join(root, relative), "utf8");
const jobs = read("components/jobsClient.jsx");
const shell = read("components/Shell.jsx");
const worlds = read("components/HostLibrary.jsx");
const polling = read("components/useAdaptivePolling.js");
const profileSaves = require("../lib/profile-saves");

assert(jobs.includes("useSyncExternalStore"), "job consumers must share one external polling store");
assert(jobs.includes("pollInFlight"), "concurrent job refreshes must be coalesced");
assert(jobs.includes('document.visibilityState === "hidden"'), "background windows must back off job polling");
assert(jobs.includes("60000"), "idle hidden job polling must be throttled");
assert(shell.includes("useJobsPoll(!isGuest)"), "guest pages must not start administrator job polling");
assert(worlds.includes("serverModeRef.current"), "server refresh must cache the settings mode gate");
assert(!read("components/PlayerWorldLibrary.jsx").includes("useAdaptivePolling"), "player Worlds must not poll dedicated server routes");
assert(polling.includes("visibilitychange"), "page pollers must respond to window visibility");
assert(polling.includes("await callback()"), "page polls must run serially rather than overlap");
for (const page of ["app/worlds/[id]/page.jsx", "app/usage/page.jsx", "app/remote-access/page.jsx"]) {
  assert(read(page).includes("useAdaptivePolling"), `${page} must use adaptive polling`);
}
assert.equal(typeof profileSaves.scanCached, "function", "profile save scans must expose the cached read path");

console.log("Performance polling and scan-cache contract: OK");
