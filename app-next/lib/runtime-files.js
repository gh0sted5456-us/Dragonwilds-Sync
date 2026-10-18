// ZIP ownership and transactional deployment shared by World and machine lanes.
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const AdmZip = require("adm-zip");
const { renameWithRetry } = require("./sync/fs-retry");

const COMPONENTS = new Set(["ue4ss-server", "ue4ss-steam", "ue4ss-gamepass", "runeschema"]);
const key = (value) => String(value).replace(/\\/g, "/").toLowerCase();
const protectedList = (value) => /(^|\/)(mods|runeschema|plugins|load_order|logicmods(?:\.lua)?\.generated)\.txt$/i.test(value);
const protectedFile = (value) => protectedList(value) || /^binaries\/win64\/version\.dll$/i.test(value);

function partsOf(value) {
  const name = String(value || "").replace(/\\/g, "/"), parts = name.split("/");
  if (!name || name.startsWith("/") || parts.some((part) => !part || part === "." || part === ".." || /[\x00-\x1f<>:"|?*]/.test(part) || /[. ]$/.test(part) || /^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(part))) throw new Error("Runtime ZIP/manifest contains an unsafe path.");
  return parts;
}

function targetFile(root, relative) {
  const base = path.resolve(root), target = path.resolve(base, ...partsOf(relative));
  if (!key(target).startsWith(key(base + path.sep))) throw new Error("Runtime path escapes its installation.");
  // Refuse junctions/symlinks. Hardlinks are safe: replace by rename, never write through them.
  let current = path.parse(target).root;
  for (const part of target.slice(current.length).split(path.sep).filter(Boolean)) {
    current = path.join(current, part);
    try { if (fs.lstatSync(current).isSymbolicLink()) throw new Error("A linked path blocks safe runtime updates: " + current); }
    catch (error) { if (error.code !== "ENOENT") throw error; }
  }
  return target;
}

function hashFile(file) {
  const hash = crypto.createHash("sha256"), buffer = Buffer.allocUnsafe(1024 * 1024);
  const fd = fs.openSync(file, "r");
  try { let count; while ((count = fs.readSync(fd, buffer, 0, buffer.length, null))) hash.update(buffer.subarray(0, count)); }
  finally { fs.closeSync(fd); }
  return hash.digest("hex");
}

function atomicJson(file, value) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const temporary = file + "." + crypto.randomBytes(6).toString("hex") + ".tmp";
  try { fs.writeFileSync(temporary, JSON.stringify(value, null, 2), { flag: "wx" }); fs.renameSync(temporary, file); }
  finally { if (fs.existsSync(temporary)) fs.unlinkSync(temporary); }
}

function readPackage(root) {
  const manifest = path.join(root, "manifest.json");
  if (!fs.existsSync(manifest) && fs.existsSync(path.join(root + ".previous", "manifest.json"))) {
    if (fs.existsSync(root)) { if (fs.readdirSync(root).length) throw new Error("An incomplete runtime package needs review: " + root); fs.rmdirSync(root); }
    fs.renameSync(root + ".previous", root);
  }
  try {
    if (fs.statSync(manifest).size > 10 * 1024 * 1024) throw new Error("Manifest exceeds the size limit.");
    const meta = JSON.parse(fs.readFileSync(manifest, "utf8"));
    if (!COMPONENTS.has(meta.component) || !Array.isArray(meta.files) || meta.files.length > 5000) throw new Error("Invalid package metadata.");
    const seen = new Set();
    for (const file of meta.files) {
      allowedRecord(meta.component, file.relative);
      if (seen.has(key(file.relative)) || !/^[a-f0-9]{64}$/i.test(file.sha256) || !Number.isSafeInteger(file.size) || file.size < 0) throw new Error("Invalid package file identity.");
      seen.add(key(file.relative));
    }
    return meta;
  }
  catch (error) { if (error.code === "ENOENT") return null; throw new Error("Runtime manifest is unreadable: " + manifest); }
}

function normalizePath(component, parts, hasSchemaFolder) {
  const lower = parts.map(key);
  if (component === "runeschema") {
    const marker = lower.lastIndexOf("runeschema");
    if (hasSchemaFolder && marker < 0) return null; // Bundled UE4SS belongs to a separate, pinned lane.
    const core = marker >= 0 ? parts.slice(marker + 1) : parts;
    if (!core.length || ["diagnostics", "logs"].includes(key(core[0]))) return null;
    if (key(core[0]) === "mods" && !(core.length === 2 && key(core[1]) === "runeschema.txt")) return null;
    return ["Binaries", "Win64", "ue4ss", "Mods", "RuneSchema", ...core];
  }
  const platformDir = component === "ue4ss-gamepass" ? "WinGDK" : "Win64";
  let relative = parts;
  const project = lower.lastIndexOf("rsdragonwilds");
  if (project >= 0) relative = parts.slice(project + 1);
  if (key(relative[0]) === "binaries") relative = relative.slice(1);
  if (["win64", "wingdk"].includes(key(relative[0]))) {
    if (key(relative[0]) !== key(platformDir)) return null;
    relative = relative.slice(1);
  }
  if (!relative.length || relative.some((part) => key(part) === "linux") || /\.(so|elf|log)$/i.test(relative.at(-1))) return null;
  if (key(relative[0]) === "ue4ss" && key(relative[1]) === "mods" && key(relative[2]) === "runeschema") return null;
  const filename = key(relative.at(-1));
  if (component === "ue4ss-server" && filename === "dwmapi.dll") return null;
  if (component !== "ue4ss-server" && filename === "version.dll") return null;
  return ["Binaries", platformDir, ...relative];
}

function allowedRecord(component, relative) {
  if (!COMPONENTS.has(component)) throw new Error("Invalid runtime component.");
  const parts = partsOf(relative), lower = key(relative);
  const platform = component === "ue4ss-gamepass" ? "wingdk" : "win64";
  if (!lower.startsWith("binaries/" + platform + "/") || /\.(exe|sav|so|elf)$/i.test(parts.at(-1))) throw new Error("Runtime file is outside its loader lane: " + relative);
  if (component === "runeschema" && !lower.startsWith("binaries/win64/ue4ss/mods/runeschema/")) throw new Error("RuneSchema manifest includes another runtime's files.");
  if (component !== "runeschema" && lower.startsWith("binaries/" + platform + "/ue4ss/mods/runeschema/")) throw new Error("UE4SS cannot own RuneSchema files.");
}

async function stagePackage(component, zipPath, parent, onProgress = () => {}, options = {}) {
  if (!COMPONENTS.has(component)) throw new Error("Choose UE4SS Server, UE4SS Steam, UE4SS Game Pass, or RuneSchema.");
  if (!zipPath || path.extname(zipPath).toLowerCase() !== ".zip" || !fs.statSync(zipPath).isFile()) throw new Error("Choose a readable runtime ZIP.");
  if (fs.statSync(zipPath).size > 512 * 1024 * 1024) throw new Error("Runtime ZIP exceeds 512 MiB.");
  const entries = new AdmZip(zipPath).getEntries().filter((entry) => !entry.isDirectory);
  if (!entries.length || entries.length > 5000) throw new Error("Runtime ZIP must contain between 1 and 5000 files.");
  const max = 1024 * 1024 * 1024;
  if (entries.some((entry) => !Number.isSafeInteger(Number(entry.header.size)) || entry.header.size < 0 || entry.header.size > 256 * 1024 * 1024)) throw new Error("Runtime ZIP contains an invalid or oversized individual file.");
  if (entries.reduce((sum, entry) => sum + Number(entry.header.size), 0) > max) throw new Error("Runtime ZIP expands beyond the 1 GiB safety limit.");
  let paths = entries.map((entry) => {
    if (((entry.header.attr >>> 16) & 0xf000) === 0xa000) throw new Error("Runtime ZIP contains a symbolic link.");
    return partsOf(entry.entryName);
  });
  const anchors = new Set(["binaries", "rsdragonwilds", "win64", "wingdk", "ue4ss", "runeschema", "dlls", "scripts", "mods"]);
  while (paths.every((parts) => parts.length > 1 && key(parts[0]) === key(paths[0][0])) && !anchors.has(key(paths[0][0]))) paths = paths.map((parts) => parts.slice(1));
  const hasSchemaFolder = paths.some((parts) => parts.some((part) => key(part) === "runeschema"));
  const hasGameLayout = paths.some((parts) => parts.some((part) => key(part) === "rsdragonwilds"));
  fs.mkdirSync(parent, { recursive: true });
  const candidate = fs.mkdtempSync(path.join(parent, ".candidate-")), records = [], seen = new Set();
  let expanded = 0;
  try {
    onProgress({ phase: "prepare", percent: 2, message: "Reading runtime archive…", line: "Reading " + path.basename(zipPath) + " (" + entries.length + " files)" });
    for (let index = 0; index < entries.length; index++) {
      if (component !== "runeschema" && hasGameLayout && !paths[index].some((part) => key(part) === "rsdragonwilds")) continue;
      const relativeParts = normalizePath(component, paths[index], hasSchemaFolder);
      if (!relativeParts) continue;
      const relative = relativeParts.join("/");
      if (component === "ue4ss-server" && key(relative) === "binaries/win64/version.dll" && options.serverBootstrap) continue;
      allowedRecord(component, relative);
      if (seen.has(key(relative))) throw new Error("Runtime ZIP has duplicate/case-colliding files: " + relative);
      seen.add(key(relative));
      const data = entries[index].getData();
      expanded += data.length;
      if (data.length !== Number(entries[index].header.size) || expanded > max) throw new Error("Runtime ZIP expanded size is invalid.");
      const output = targetFile(path.join(candidate, "files"), relative);
      fs.mkdirSync(path.dirname(output), { recursive: true }); fs.writeFileSync(output, data, { flag: "wx" });
      records.push({ relative, size: data.length, sha256: hashFile(output), clientEligible: component !== "ue4ss-server", preserve: protectedFile(relative) });
      const percent = Math.max(3, Math.round((index + 1) / entries.length * 70));
      onProgress({ phase: "install", percent, message: "Staging loader files…", line: "[" + percent + "%] " + relative });
      if (index % 8 === 7) await new Promise((resolve) => setImmediate(resolve));
    }
    const contains = (relative) => seen.has(key(relative));
    const bin = "Binaries/" + (component === "ue4ss-gamepass" ? "WinGDK" : "Win64");
    if (component.startsWith("ue4ss-") && !contains(bin + "/ue4ss/UE4SS.dll")) throw new Error("This is not a complete UE4SS ZIP: ue4ss/UE4SS.dll was not found for this platform.");
    if (component === "ue4ss-server" && options.serverBootstrap) {
      const relative = bin + "/version.dll", output = targetFile(path.join(candidate, "files"), relative);
      if (!fs.statSync(options.serverBootstrap).isFile()) throw new Error("The retained server version.dll is not a file.");
      fs.mkdirSync(path.dirname(output), { recursive: true }); fs.copyFileSync(options.serverBootstrap, output);
      records.push({ relative, size: fs.statSync(output).size, sha256: hashFile(output), clientEligible: false, preserve: true, origin: "retained-server-bootstrap" });
      seen.add(key(relative));
    }
    if (component === "ue4ss-server" && !contains(bin + "/version.dll")) throw new Error("Dedicated-server UE4SS requires version.dll already installed, or a server ZIP containing the initial bootstrap. Existing version.dll is never replaced.");
    if (component === "ue4ss-steam" && !contains(bin + "/dwmapi.dll")) throw new Error("Steam UE4SS requires dwmapi.dll.");
    if (component === "ue4ss-gamepass" && !records.some((record) => /^binaries\/wingdk\/[^/]+\.dll$/i.test(record.relative))) throw new Error("PC Game Pass UE4SS requires its WinGDK bootstrap DLL.");
    if (component === "runeschema" && !contains(bin + "/ue4ss/Mods/RuneSchema/dlls/main.dll")) throw new Error("This is not a complete RuneSchema ZIP: dlls/main.dll was not found.");
    if (component === "runeschema" && !contains(bin + "/ue4ss/Mods/RuneSchema/enabled.txt")) {
      const relative = bin + "/ue4ss/Mods/RuneSchema/enabled.txt", output = targetFile(path.join(candidate, "files"), relative);
      fs.writeFileSync(output, ""); records.push({ relative, size: 0, sha256: hashFile(output), clientEligible: true });
    }
    records.sort((left, right) => key(left.relative).localeCompare(key(right.relative)));
    const meta = { schema: "RSDWSync.RuntimePackage.v2", component, archive: path.basename(zipPath), archiveSha256: hashFile(zipPath), installedAt: Date.now(), files: records };
    atomicJson(path.join(candidate, "manifest.json"), meta);
    onProgress({ phase: "verify", percent: 78, message: "ZIP verified; manifest generated", line: "Verified " + records.length + " files; existing mod lists will be preserved." });
    return candidate;
  } catch (error) { fs.rmSync(candidate, { recursive: true, force: true }); throw error; }
}

async function promotePackage(candidate, permanent, deploy = () => {}) {
  const previous = permanent + ".previous";
  if (fs.existsSync(previous)) {
    if (!fs.existsSync(permanent)) await renameWithRetry(previous, permanent);
    else fs.rmSync(previous, { recursive: true, force: true });
  }
  let promoted = false, parked = false;
  try {
    if (fs.existsSync(permanent)) { await renameWithRetry(permanent, previous); parked = true; }
    await renameWithRetry(candidate, permanent); promoted = true;
    await deploy();
  } catch (error) {
    if (promoted) fs.rmSync(permanent, { recursive: true, force: true });
    if (parked) await renameWithRetry(previous, permanent);
    throw error;
  }
  // Retain one previous package; replace that recovery copy on the next update.
}

function applyFiles({ gameRoot, desired, previous = [], retained = [], ledgerFile, assertStopped = () => {}, onProgress = () => {} }) {
  const map = new Map();
  for (const file of retained) allowedRecord(file.component, file.relative);
  for (const file of desired) {
    // RuneSchema is stored canonically in Win64 and mapped to WinGDK at deployment.
    allowedRecord(file.component, file.component === "runeschema" ? file.relative.replace(/^Binaries\/WinGDK\//i, "Binaries/Win64/") : file.relative);
    if (!/^[a-f0-9]{64}$/i.test(file.sha256) || !Number.isSafeInteger(file.size) || file.size < 0) throw new Error("Invalid runtime file identity.");
    if (map.has(key(file.relative))) throw new Error("Two runtime packages own the same file.");
    if (hashFile(file.source) !== file.sha256 || fs.statSync(file.source).size !== file.size) throw new Error("Runtime cache verification failed: " + file.relative);
    map.set(key(file.relative), file);
  }
  const recoveryBase = ledgerFile + ".recovery", pendingFile = ledgerFile + ".pending";
  const undo = (receipt) => {
    if (!/^[a-f0-9]{16}$/.test(receipt.id) || !Array.isArray(receipt.operations)) throw new Error("Invalid runtime recovery journal.");
    if (key(receipt.gameRoot) !== key(path.resolve(gameRoot))) throw new Error("Runtime recovery belongs to another installation.");
    for (const operation of [...receipt.operations].reverse()) {
      if (!/^binaries\/(win64|wingdk)\//i.test(operation.relative) || /\.(exe|sav)$/i.test(operation.relative)) throw new Error("Unsafe file in runtime recovery journal.");
      const target = targetFile(gameRoot, operation.relative);
      if (operation.existed) {
        const backup = targetFile(recoveryBase, receipt.id + "/" + operation.relative);
        if (!fs.existsSync(backup)) throw new Error("Runtime recovery file is missing: " + operation.relative);
        fs.mkdirSync(path.dirname(target), { recursive: true });
        const temp = target + ".rsdw-restore-" + receipt.id;
        fs.copyFileSync(backup, temp); fs.renameSync(temp, target);
      } else if (fs.existsSync(target)) {
        if (operation.sha256 && hashFile(target) !== operation.sha256) throw new Error("Recovery found a newly edited file; it was preserved: " + operation.relative);
        fs.unlinkSync(target);
      }
    }
    if (receipt.oldLedger === null) { if (fs.existsSync(ledgerFile)) fs.unlinkSync(ledgerFile); }
    else atomicJson(ledgerFile, receipt.oldLedger);
  };
  assertStopped();
  if (fs.existsSync(pendingFile)) {
    undo(JSON.parse(fs.readFileSync(pendingFile, "utf8"))); fs.unlinkSync(pendingFile);
    throw new Error("Recovered an interrupted loader update. Retry the ZIP update.");
  }
  const operations = [], retired = new Set(), retainedKeys = new Set(retained.map((file) => key(file.relative)));
  const prior = new Set(previous.map(key));
  for (const component of new Set(desired.map((file) => file.component))) {
    const opposite = component === "ue4ss-server" ? "Binaries/Win64/dwmapi.dll" : component === "ue4ss-steam" ? "Binaries/Win64/version.dll" : null;
    if (opposite && fs.existsSync(targetFile(gameRoot, opposite)) && (component === "ue4ss-steam" || !prior.has(key(opposite)))) throw new Error("Another, unmanaged loader bootstrap exists: " + opposite + ". Review it before updating; RSDW will not load two bootstraps or delete unknown files.");
  }
  for (const relative of previous) {
    if (protectedFile(relative) || map.has(key(relative)) || retainedKeys.has(key(relative)) || retired.has(key(relative))) continue;
    const parts = partsOf(relative);
    if (key(parts[0]) !== "binaries" || !["win64", "wingdk"].includes(key(parts[1])) || /\.(exe|sav)$/i.test(parts.at(-1))) throw new Error("Previous runtime ledger contains an unsafe file.");
    retired.add(key(relative));
    if (fs.existsSync(targetFile(gameRoot, relative))) operations.push({ relative, action: "remove" });
  }
  for (const file of desired) {
    const target = targetFile(gameRoot, file.relative);
    if (protectedFile(file.relative) && fs.existsSync(target)) continue;
    const marker = file.relative.match(/^(.+\/ue4ss\/Mods)\/([^/]+)\/enabled\.txt$/i);
    if (marker) {
      if (fs.existsSync(target) || fs.existsSync(target + ".rsdw-disabled")) continue;
      const modsDir = targetFile(gameRoot, marker[1]);
      if (require("./loader-mods").state(modsDir, "ue4ss", marker[2], path.dirname(target)).loaderEnabled === false) continue;
    }
    if (fs.existsSync(target) && fs.statSync(target).isFile() && hashFile(target) === file.sha256) continue;
    operations.push({ relative: file.relative, action: "replace", source: file.source, sha256: file.sha256 });
  }
  const id = crypto.randomBytes(8).toString("hex");
  for (const operation of operations) {
    const target = targetFile(gameRoot, operation.relative);
    operation.existed = fs.existsSync(target);
    if (operation.existed) {
      if (!fs.lstatSync(target).isFile()) throw new Error("A folder occupies a runtime file path: " + operation.relative);
      const backup = targetFile(recoveryBase, id + "/" + operation.relative);
      fs.mkdirSync(path.dirname(backup), { recursive: true }); fs.copyFileSync(target, backup);
    }
  }
  const oldLedger = fs.existsSync(ledgerFile) ? JSON.parse(fs.readFileSync(ledgerFile, "utf8")) : null;
  const receipt = { id, gameRoot: path.resolve(gameRoot), operations, oldLedger, createdAt: Date.now() };
  assertStopped();
  atomicJson(pendingFile, receipt);
  try {
    for (let index = 0; index < operations.length; index++) {
      const operation = operations[index], target = targetFile(gameRoot, operation.relative);
      if (operation.action === "remove") fs.unlinkSync(target);
      else {
        fs.mkdirSync(path.dirname(target), { recursive: true });
        const temporary = target + ".rsdw-runtime-" + id;
        try { fs.copyFileSync(operation.source, temporary); fs.renameSync(temporary, target); }
        finally { if (fs.existsSync(temporary)) fs.unlinkSync(temporary); }
      }
      onProgress({ phase: "install", percent: Math.round(80 + (index + 1) / Math.max(1, operations.length) * 18), message: "Replacing loader-owned files…", line: (operation.action === "remove" ? "Removed retired file " : "Installed ") + operation.relative });
    }
    const defaults = [...new Set([...(oldLedger?.defaults || []), ...previous.filter(protectedFile), ...desired.filter((file) => protectedFile(file.relative)).map((file) => file.relative)])];
    atomicJson(ledgerFile, { schema: "RSDWSync.RuntimeDeployment.v1", gameRoot: path.resolve(gameRoot), installedAt: Date.now(), files: desired.filter((file) => !protectedFile(file.relative)).map(({ relative, sha256, size, component }) => ({ relative, sha256, size, component })).concat(retained), defaults, recovery: id });
    fs.unlinkSync(pendingFile);
  } catch (error) {
    try { undo(receipt); fs.unlinkSync(pendingFile); }
    catch (recoveryError) { throw new Error(error.message + " Recovery needs attention: " + recoveryError.message); }
    throw error;
  }
  try { if (fs.existsSync(recoveryBase)) {
    const folders = fs.readdirSync(recoveryBase).filter((name) => /^[a-f0-9]{16}$/.test(name)).map((name) => ({ name, at: fs.statSync(path.join(recoveryBase, name)).mtimeMs })).sort((a, b) => b.at - a.at);
    for (const folder of folders.slice(3)) fs.rmSync(path.join(recoveryBase, folder.name), { recursive: true, force: true });
  } } catch { /* Recovery retention must never turn a committed update into a failure. */ }
  return { changed: operations.length, removed: operations.filter((operation) => operation.action === "remove").length, recovery: id };
}

module.exports = { COMPONENTS, stagePackage, promotePackage, readPackage, targetFile, protectedList, protectedFile, hashFile, atomicJson, applyFiles };
