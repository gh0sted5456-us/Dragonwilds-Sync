const assert = require("assert");
const fs = require("fs");
const path = require("path");
const postcss = require("postcss");
const { SETTINGS_SECTIONS, readSettingsSection, settingsSectionUrl, workspaceTrail } = require("../lib/ui-navigation");
const { windowPalette } = require("../electron/window-theme");
const read = (file) => fs.readFileSync(path.join(__dirname, "..", file), "utf8");

for (const section of SETTINGS_SECTIONS) {
  assert.equal(readSettingsSection(`?section=${section}`), section);
  assert.equal(readSettingsSection(settingsSectionUrl("http://localhost/settings?keep=1#tools", section).split("?")[1].split("#")[0]), section);
}
assert.equal(readSettingsSection("?section=obsolete"), null);
assert.equal(settingsSectionUrl("http://localhost/settings?section=appearance&keep=1#tools", null), "/settings?keep=1#tools");
assert.equal(workspaceTrail("/save-cleaner").area, "Settings");
assert.equal(workspaceTrail("/worlds/fixture").href, "/host");
assert.equal(workspaceTrail("/worlds/fixture").area, "Host");
assert.equal(workspaceTrail("/host").area, "Host");
assert.equal(workspaceTrail("/profiles/fixture/server").area, "Host");
assert.equal(workspaceTrail("/profiles/fixture/player").label, "World profile");
assert.equal(workspaceTrail("/profile").label, "Player identity");
assert.equal(workspaceTrail("/downloads").area, "Downloads");
assert.equal(workspaceTrail("/socials").area, "Community");

const css = read("app/globals.css");
postcss.parse(css); // All responsive/container rules must be valid CSS.
for (const theme of ["dark", "gilded", "amethyst", "ember", "frost"]) {
  const native = windowPalette(theme);
  assert.equal(native.height, 46);
  assert(/^#[a-f0-9]{6}$/i.test(native.color));
  assert(css.includes(native.color) && css.includes(native.symbolColor), `native caption doesn't match ${theme}`);
  assert(read("components/ThemeProvider.jsx").includes(`id: "${theme}"`));
  assert(read("app/layout.js").includes(`'${theme}'`), `theme ${theme} is missing from first-paint restoration`);
}
assert.deepEqual(windowPalette("__proto__"), windowPalette("dark"));
assert.deepEqual(windowPalette({ color: "unsafe" }), windowPalette("dark"));
const palette = windowPalette("dark"); palette.color = "unsafe";
assert.equal(windowPalette("dark").color, "#050505", "palette results must not mutate the allow-list");

const shell = read("components/Shell.jsx");
assert(shell.includes('aria-label="Workspace navigation"') && shell.includes('className="skip-link"'));
assert(shell.includes('aria-current={active ? "page" : undefined}'), "navigation must expose its current destination");
assert(!shell.includes('label: "Profiles"') && shell.includes('label: "Host"') && shell.includes('label: "Community"'));
assert(shell.includes('href="/profile"'), "footer profile management must stay available");
assert(shell.includes('"/save-cleaner"'), "Save tools must stay under Settings navigation");
assert(!shell.includes('ver?.current || "0.1.1"'), "never show a stale fallback version during loading");
const settings = read("app/settings/page.jsx");
assert(settings.includes('addEventListener("popstate", restore)') && settings.includes('removeEventListener("popstate", restore)'));
assert(settings.includes("CATEGORY_GROUPS") && settings.includes("Settings could not be loaded"));
const home = read("components/PlayerWorldLibrary.jsx");
assert(!home.includes('api("/api/worlds")') && !home.includes("CreateWorldModal") && !home.includes("useAdaptivePolling"), "player Worlds must not load or poll hosting");
assert(read("app/page.jsx").includes('redirect("/host")'), "old hosting bookmarks must redirect to Host");
assert(read("app/host/page.jsx").includes("HostLibrary"));
assert(!read("app/globals.css").includes(".worlds-mode-switch"), "obsolete combined mode selector styles must stay removed");
assert(home.includes("Show the cached library immediately") && home.includes("void loadProfiles();"), "cached Worlds must not wait for remote heartbeat responses");
assert(home.includes("setConnectOpen(false); setScanOpen") && home.includes("setScanOpen(false); setConnectOpen"), "connect and scan flows must not overlap");
const detail = read("app/worlds/[id]/page.jsx");
assert(detail.includes('className="server-diagnostics" open={tab === "overview"}'));
assert(detail.includes('label: "Profile & launch"'));
assert(detail.includes("Only the active panel is mounted"), "the cleanup must not revive hidden polling panels");
assert(read("components/PageChrome.jsx").includes('tabIndex={index === selectedIndex ? 0 : -1}'));
assert(read("electron/preload.js").includes('ipcRenderer.invoke("window-theme", theme)'));
console.log("RSDW UI flow: separate Worlds/Host, footer identity, route/history mapping, themes, responsive CSS and navigation: OK");
