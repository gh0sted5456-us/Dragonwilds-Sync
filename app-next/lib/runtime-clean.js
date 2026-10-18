// Explicit, reviewed cleanup is broader than normal manifest-owned ZIP updates.
// Never walk the selected loader's direct Mods folder, or touch sibling proxies.
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const files = require("./runtime-files");
const { P } = require("./paths");
const key = (value) => path.resolve(value).toLowerCase();
const tick = () => new Promise((resolve) => setImmediate(resolve));

function loaderRelative(component, platform) {
  if (!files.COMPONENTS.has(component)) throw new Error("Invalid runtime component.");
  const bin = component === "ue4ss-gamepass" || (component === "runeschema" && platform === "gamepass") ? "WinGDK" : "Win64";
  return "Binaries/" + bin + "/ue4ss" + (component === "runeschema" ? "/Mods/RuneSchema" : "");
}
function stateFile(scope) {
  return path.join(P.data(), "runtime-clean-state", crypto.createHash("sha256").update(scope).digest("hex") + ".json");
}
function readState(scope) {
  try { return JSON.parse(fs.readFileSync(stateFile(scope), "utf8")); }
  catch (error) { if (error.code === "ENOENT") return null; throw error; }
}
function descriptor(spec) {
  if (!spec.scope || !spec.targets.length || spec.targets.some((target) => !/^[a-z-]+$/.test(target.id))) throw new Error("Invalid cleanup scope.");
  const targets = spec.targets.map((target) => ({ id: target.id, root: files.targetFile(target.gameRoot, loaderRelative(spec.component, target.platform)) }));
  for (let a = 0; a < targets.length; a++) for (let b = a + 1; b < targets.length; b++) if (key(targets[a].root) === key(targets[b].root) || key(targets[a].root).startsWith(key(targets[b].root) + path.sep) || key(targets[b].root).startsWith(key(targets[a].root) + path.sep)) throw new Error("Cleanup targets overlap.");
  return targets;
}
function metadataSnapshot(spec) {
  return spec.metadata.map((file) => {
    let sha256 = null;
    if (fs.existsSync(file)) {
      if (!fs.lstatSync(file).isFile() || fs.statSync(file).size > 10 * 1024 * 1024) throw new Error("Cleanup metadata needs review: " + file);
      sha256 = files.hashFile(file);
    }
    return { file, sha256 };
  });
}
async function preview(spec) {
  const targets = descriptor(spec), entries = [], directories = [];
  for (const target of targets) {
    async function visit(directory, relative = "") {
      if (!fs.existsSync(directory)) return;
      const stat = fs.lstatSync(directory);
      if (!stat.isDirectory() || stat.isSymbolicLink()) throw new Error("A linked/non-directory runtime path blocks cleanup: " + directory);
      directories.push(target.id + "/" + relative);
      for (const child of fs.readdirSync(directory, { withFileTypes: true })) {
        if (!relative && child.name.toLowerCase() === "mods") continue;
        const next = relative ? relative + "/" + child.name : child.name;
        const full = files.targetFile(target.root, next), info = fs.lstatSync(full);
        if (info.isDirectory()) await visit(full, next);
        else if (info.isFile()) {
          entries.push({ target: target.id, relative: next, size: info.size, sha256: files.hashFile(full) });
          if (entries.length > 20000) throw new Error("Runtime cleanup exceeds 20,000 files; review this folder manually.");
          if (entries.length % 8 === 0) await tick();
        } else throw new Error("Unsupported runtime file blocks cleanup: " + full);
      }
    }
    await visit(target.root);
  }
  entries.sort((a, b) => (a.target + "/" + a.relative).localeCompare(b.target + "/" + b.relative));
  directories.sort();
  const metadata = metadataSnapshot(spec);
  const fingerprint = crypto.createHash("sha256").update(JSON.stringify({ scope: spec.scope, targets, entries, directories, metadata })).digest("hex");
  return { component: spec.component, targets, entries, directories, metadata, fingerprint, files: entries.length, bytes: entries.reduce((sum, entry) => sum + entry.size, 0), preserved: targets.map((target) => path.join(target.root, "Mods")), recovery: readState(spec.scope) };
}
function snapshotPath(id) {
  if (!/^[a-f0-9-]{36}$/i.test(id)) throw new Error("Invalid cleanup recovery ID.");
  return path.join(P.data(), "runtime-clean-recovery", id);
}
function entryFile(roots, entry) {
  if (String(entry.relative).replace(/\\/g, "/").split("/")[0].toLowerCase() === "mods") throw new Error("Cleanup may never touch the preserved Mods folder.");
  const root = roots.find((target) => target.id === entry.target);
  if (!root) throw new Error("Cleanup file references another target.");
  return files.targetFile(root.root, entry.relative);
}
function backupFile(backup, entry) { return files.targetFile(backup, "files/" + entry.target + "/" + entry.relative); }
function verifyScope(spec, receipt) {
  if (spec.scope !== receipt.scope || spec.component !== receipt.component) throw new Error("Recovery belongs to another runtime.");
  if (JSON.stringify(descriptor(spec)) !== JSON.stringify(receipt.before.targets)) throw new Error("The installation moved; review the original recovery folder before restoring.");
  if (JSON.stringify(spec.metadata) !== JSON.stringify(receipt.before.metadata.map((entry) => entry.file))) throw new Error("Recovery metadata does not match this runtime.");
}
async function restoreFiles(spec, receipt, backup, selected = receipt.before.entries, selectedMetadata = receipt.before.metadata) {
  verifyScope(spec, receipt);
  // Validate every backup before restoring any file.
  for (const entry of selected) if (files.hashFile(backupFile(backup, entry)) !== entry.sha256) throw new Error("Cleanup backup failed verification: " + entry.relative);
  for (const entry of selectedMetadata) {
    const index = receipt.before.metadata.findIndex((meta) => meta.file === entry.file);
    if (entry.sha256 && files.hashFile(path.join(backup, "metadata", index + ".json")) !== entry.sha256) throw new Error("Cleanup metadata backup is corrupt.");
  }
  for (let index = 0; index < selected.length; index++) {
    const entry = selected[index], target = entryFile(receipt.before.targets, entry);
    if (fs.existsSync(target)) {
      if (files.hashFile(target) !== entry.sha256) throw new Error("Restoration found an edited runtime file; it was preserved: " + entry.relative);
      continue;
    }
    fs.mkdirSync(path.dirname(target), { recursive: true });
    const temporary = target + ".rsdw-clean-restore";
    try {
      fs.copyFileSync(backupFile(backup, entry), temporary);
      if (fs.existsSync(target) && files.hashFile(target) !== entry.sha256) throw new Error("A runtime file changed during restoration; it was preserved.");
      fs.renameSync(temporary, target);
    }
    finally { if (fs.existsSync(temporary)) fs.unlinkSync(temporary); }
    if (index % 8 === 7) await tick();
  }
  for (const entry of selectedMetadata) {
    const index = receipt.before.metadata.findIndex((meta) => meta.file === entry.file), saved = path.join(backup, "metadata", index + ".json");
    const change = receipt.changes.find((item) => item.file === entry.file);
    const afterHash = change && crypto.createHash("sha256").update(JSON.stringify(change.value, null, 2)).digest("hex");
    const currentHash = fs.existsSync(entry.file) ? files.hashFile(entry.file) : null;
    if (currentHash !== entry.sha256 && currentHash !== afterHash) throw new Error("Runtime metadata was edited during restoration; it was preserved.");
    if (entry.sha256 === null) { if (fs.existsSync(entry.file)) fs.unlinkSync(entry.file); }
    else {
      if (files.hashFile(saved) !== entry.sha256) throw new Error("Cleanup metadata backup is corrupt.");
      fs.mkdirSync(path.dirname(entry.file), { recursive: true }); fs.copyFileSync(saved, entry.file);
    }
  }
}
async function clean(spec, fingerprint, changes, onProgress = () => {}) {
  spec.assertStopped();
  const pending = readState(spec.scope);
  if (["pending", "restoring", "needs-recovery"].includes(pending?.state)) throw new Error("Restore the interrupted cleanup before cleaning or reinstalling this runtime.");
  const before = await preview(spec);
  if (!/^[a-f0-9]{64}$/.test(String(fingerprint)) || before.fingerprint !== fingerprint) throw new Error("Runtime files changed since review. Preview the cleanup again.");
  if (changes.some((change) => !spec.metadata.includes(change.file))) throw new Error("Cleanup attempted to change unreviewed metadata.");
  const id = crypto.randomUUID(), backup = snapshotPath(id);
  for (const target of before.targets) if (key(backup).startsWith(key(target.root) + path.sep)) throw new Error("Cleanup recovery storage must be outside the runtime folder.");
  const receipt = { schema: "RSDWSync.RuntimeClean.v1", id, scope: spec.scope, component: spec.component, before, changes, state: "backing-up", at: Date.now() };
  fs.mkdirSync(backup, { recursive: true });
  for (let index = 0; index < before.entries.length; index++) {
    const entry = before.entries[index], target = backupFile(backup, entry);
    fs.mkdirSync(path.dirname(target), { recursive: true }); fs.copyFileSync(entryFile(before.targets, entry), target);
    if (files.hashFile(target) !== entry.sha256) throw new Error("Cleanup backup changed: " + entry.relative);
    onProgress({ phase: "backup", percent: Math.round((index + 1) / Math.max(1, before.files) * 45), message: "Backing up runtime files…", line: "Backed up " + entry.target + "/" + entry.relative });
    if (index % 8 === 7) await tick();
  }
  for (let index = 0; index < before.metadata.length; index++) {
    const entry = before.metadata[index];
    if (entry.sha256) {
      const output = path.join(backup, "metadata", index + ".json");
      fs.mkdirSync(path.dirname(output), { recursive: true }); fs.copyFileSync(entry.file, output);
      if (files.hashFile(output) !== entry.sha256) throw new Error("Cleanup metadata changed during backup.");
    }
  }
  if ((await preview(spec)).fingerprint !== fingerprint) throw new Error("Runtime files changed during backup. Nothing was cleaned.");
  spec.assertStopped();
  receipt.state = "pending";
  files.atomicJson(path.join(backup, "receipt.json"), receipt);
  files.atomicJson(stateFile(spec.scope), { id, state: "pending", backup, at: receipt.at });
  const removed = [], writtenMetadata = [];
  try {
    for (let index = 0; index < before.entries.length; index++) {
      const entry = before.entries[index];
      const source = entryFile(before.targets, entry);
      if (files.hashFile(source) !== entry.sha256) throw new Error("Runtime changed while cleaning; the changed file was preserved: " + entry.relative);
      fs.unlinkSync(source); removed.push(entry);
      onProgress({ phase: "cleanup", percent: Math.round(45 + (index + 1) / Math.max(1, before.files) * 50), message: "Clearing runtime; preserving Mods…", line: "Cleared " + entry.target + "/" + entry.relative });
      if (index % 8 === 7) await tick();
    }
    for (const change of changes) {
      const old = before.metadata.find((entry) => entry.file === change.file);
      const current = fs.existsSync(change.file) ? files.hashFile(change.file) : null;
      if (old.sha256 !== current) throw new Error("Runtime metadata changed while cleaning.");
      files.atomicJson(change.file, change.value); writtenMetadata.push(old);
    }
    receipt.after = await preview(spec); receipt.state = "cleaned";
    files.atomicJson(path.join(backup, "receipt.json"), receipt);
    files.atomicJson(stateFile(spec.scope), { id, state: "cleaned", backup, at: receipt.at });
  } catch (error) {
    try {
      await restoreFiles(spec, receipt, backup, removed, writtenMetadata);
      files.atomicJson(stateFile(spec.scope), { id, state: "rolled-back", backup, at: receipt.at });
    } catch (restoreError) {
      files.atomicJson(stateFile(spec.scope), { id, state: "needs-recovery", backup, at: receipt.at });
      throw new Error(error.message + " Recovery needs attention: " + restoreError.message);
    }
    throw error;
  }
  onProgress({ phase: "finalizing", percent: 100, message: "Runtime cleared; install a ZIP to refill it", line: "Kept Mods and the directory structure. Recovery backup: " + backup });
  return { files: before.files, bytes: before.bytes, recovery: readState(spec.scope) };
}
async function restore(spec, id, onProgress = () => {}) {
  spec.assertStopped();
  const backup = snapshotPath(id), state = readState(spec.scope);
  if (state?.id !== id || !["cleaned", "pending", "restoring", "needs-recovery"].includes(state.state)) throw new Error("This cleanup is not available for restoration.");
  const receipt = JSON.parse(fs.readFileSync(path.join(backup, "receipt.json"), "utf8"));
  verifyScope(spec, receipt);
  const current = await preview(spec);
  if (state.state === "cleaned" && receipt.after && receipt.after.fingerprint !== current.fingerprint) throw new Error("Runtime files changed after cleanup. Restore was blocked to avoid overwriting a newer ZIP or edited files.");
  if (state.state !== "cleaned" || !receipt.after) {
    const old = new Map(receipt.before.entries.map((entry) => [entry.target + "/" + entry.relative, entry.sha256]));
    for (const entry of current.entries) if (old.get(entry.target + "/" + entry.relative) !== entry.sha256) throw new Error("Runtime files changed after the interrupted cleanup; review recovery manually.");
    for (const meta of current.metadata) {
      const before = receipt.before.metadata.find((entry) => entry.file === meta.file);
      const change = receipt.changes.find((entry) => entry.file === meta.file);
      const after = change && crypto.createHash("sha256").update(JSON.stringify(change.value, null, 2)).digest("hex");
      if (meta.sha256 !== before.sha256 && meta.sha256 !== after) throw new Error("Runtime metadata changed after the interrupted cleanup.");
    }
  }
  spec.assertStopped();
  files.atomicJson(stateFile(spec.scope), { id, state: "restoring", backup, at: Date.now() });
  try { await restoreFiles(spec, receipt, backup); }
  catch (error) {
    files.atomicJson(stateFile(spec.scope), { id, state: "needs-recovery", backup, at: Date.now() });
    throw error;
  }
  files.atomicJson(stateFile(spec.scope), { id, state: "restored", backup, at: Date.now() });
  onProgress({ phase: "finalizing", percent: 100, message: "Runtime restored", line: "Restored cleanup backup without changing Mods." });
  return { files: receipt.before.files, recovery: readState(spec.scope) };
}

module.exports = { loaderRelative, preview, clean, restore, readState };
