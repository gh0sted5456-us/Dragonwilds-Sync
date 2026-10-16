const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");
const root = path.resolve(__dirname, "..");
function run(args) {
  const result = spawnSync(process.execPath, args, { cwd: root, stdio: "inherit", windowsHide: true, timeout: 180000 });
  if (result.status !== 0) { console.error(`Release check failed: ${args.join(" ")}`); process.exit(result.status || 1); }
}
for (const file of fs.readdirSync(path.join(root, "electron")).filter((name) => name.endsWith(".js"))) run(["--check", `electron/${file}`]);
const checks = fs.readdirSync(__dirname).filter((name) => /^check-.*\.js$/.test(name) && name !== path.basename(__filename)).sort();
console.log(`Running ${checks.length} isolated release regression checks`);
for (const check of checks) run([`scripts/${check}`]);
console.log(`All ${checks.length} release regression checks passed.`);
