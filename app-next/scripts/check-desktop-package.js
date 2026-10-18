const assert = require("assert");
const fs = require("fs");
const path = require("path");
const { builtinModules } = require("module");
const { getNodeModuleFileMatcher } = require("app-builder-lib/out/fileMatcher");
const root = path.resolve(__dirname, "..");
const pkg = require("../package.json");
const shell = path.join(root, "electron");
const builtins = new Set(builtinModules.map((id) => id.replace(/^node:/, "")));

// Removing the duplicate app.asar dependency tree is safe only while the desktop
// shell uses Electron, Node built-ins and its own relative JS modules. Fail a
// future release if a new external dependency needs an explicit packaging policy.
for (const name of fs.readdirSync(shell).filter((name) => name.endsWith(".js"))) {
  const source = fs.readFileSync(path.join(shell, name), "utf8");
  const calls = [...source.matchAll(/\brequire\(\s*(["'])([^"']+)\1\s*\)/g)];
  assert.equal(calls.length, [...source.matchAll(/\brequire\s*\(/g)].length, `${name}: review dynamic desktop imports before shipping`);
  for (const [, , id] of calls) {
    if (id.startsWith(".")) {
      const target = path.resolve(shell, id.endsWith(".js") ? id : `${id}.js`);
      assert.equal(path.dirname(target), shell);
      assert(fs.existsSync(target), `${name}: missing desktop module ${id}`);
    } else assert(id === "electron" || builtins.has(id.replace(/^node:/, "")), `${name}: external ${id} would need to be bundled`);
  }
}
const matcher = getNodeModuleFileMatcher(root, path.join(root, "release/contract"), (value) => value, {}, { config: pkg.build, debugLogger: { isEnabled: false } });
const filter = matcher.createFilter();
for (const relative of ["node_modules", "node_modules/next/package.json", "node_modules/monaco-editor/package.json", "node_modules/adm-zip/package.json"]) {
  const file = path.join(root, relative);
  assert(!filter(file, fs.statSync(file)), `Duplicate shell dependency would be shipped: ${relative}`);
}
assert(pkg.build.files.includes("electron/**/*") && pkg.build.files.includes("package.json"));
assert(pkg.build.extraResources.some((entry) => entry.from === "dist-standalone" && entry.to === "app"), "The independent interface runtime must remain bundled");
const detail = fs.readFileSync(path.join(root, "app/worlds/[id]/page.jsx"), "utf8");
for (const panel of ["LogsPanel", "ModsPanel", "SettingsEditor", "BackupsPanel", "SchedulePanel", "AdminPanel", "CustomizeModal"]) {
  assert(detail.includes(`const ${panel} = dynamic(() => import("@/components/${panel}")`), `${panel}: keep secondary tools out of initial overview code`);
}
assert(detail.includes("TabPanelBoundary") && detail.includes('tab === "console"'), "Lazy loading must retain active-only mounts and error boundaries");
console.log("Lean Electron shell: real builder excludes duplicate dependencies, all desktop imports remain resolvable, standalone runtime retained and secondary server tools split into lazy chunks: OK");
