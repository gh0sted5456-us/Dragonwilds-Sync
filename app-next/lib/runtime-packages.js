const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const AdmZip = require("adm-zip");
const dbm = require("./db");
const { P } = require("./paths");

const COMPONENTS = new Set(["ue4ss-server", "ue4ss-steam", "ue4ss-gamepass", "runeschema"]);

function sha256File(file) {
  const hash = crypto.createHash("sha256");
  hash.update(fs.readFileSync(file));
  return hash.digest("hex");
}
function safeParts(name) {
  const clean = String(name || "").replace(/\\/g, "/").replace(/^\/+|\/+$/g, "");
  const parts = clean.split("/").filter(Boolean);
  if (!parts.length || parts.some((p) => p === "." || p === ".." || /[<>:"|?*]/.test(p))) throw new Error("Runtime ZIP contains an unsafe path.");
  return parts;
}
function stripWrapper(rows) {
  if (rows.length && rows.every((parts) => parts.length > 1 && parts[0].toLowerCase() === rows[0][0].toLowerCase())) return rows.map((parts) => parts.slice(1));
  return rows;
}
function serverGameRoot(installDir) {
  const nested = path.join(installDir, "RSDragonwilds");
  return fs.existsSync(nested) ? nested : installDir;
}
function normalizeRuntimePath(component, parts) {
  const lower = parts.map((p) => p.toLowerCase());
  if (component.startsWith("ue4ss-")) {
    if (lower.includes("linux") || /\.(so|elf)$/i.test(parts[parts.length - 1])) return null;
    const platformDir = component === "ue4ss-gamepass" ? "WinGDK" : "Win64";
    let rel = parts;
    if (lower[0] === "binaries" && ["win64","wingdk"].includes(lower[1])) rel = parts.slice(2);
    else if (["win64","wingdk"].includes(lower[0])) rel = parts.slice(1);
    const relLower = rel.map((p) => p.toLowerCase());
    if (relLower[0] === "ue4ss" && relLower[1] === "mods") return null;
    const filename = rel[rel.length - 1]?.toLowerCase();
    // Dedicated Dragonwilds servers use version.dll as the UE4SS bootstrap.
    // Retail Steam clients use dwmapi.dll. Never allow one lane's bootstrap
    // to bleed into the other.
    if (component === "ue4ss-server" && filename === "dwmapi.dll") return null;
    if (component !== "ue4ss-server" && filename === "version.dll") return null;
    return ["Binaries", platformDir, ...rel];
  }
  const marker = lower.lastIndexOf("runeschema");
  const core = marker >= 0 ? parts.slice(marker + 1) : parts;
  if (!core.length || ["mods", "diagnostics"].includes(core[0].toLowerCase())) return null;
  return ["Binaries", "Win64", "ue4ss", "Mods", "RuneSchema", ...core];
}
function manifestPath(worldId, component) { return path.join(P.worldRuntimeDir(worldId, component), "manifest.json"); }
function filesRoot(worldId, component) { return path.join(P.worldRuntimeDir(worldId, component), "files"); }
function readManifest(worldId, component) {
  try { return JSON.parse(fs.readFileSync(manifestPath(worldId, component), "utf8")); } catch { return null; }
}
function localTarget(root, relative) {
  const base = path.resolve(root);
  const target = path.resolve(base, ...String(relative).split("/"));
  const prefix = base.endsWith(path.sep) ? base : base + path.sep;
  if (target !== base && !target.toLowerCase().startsWith(prefix.toLowerCase())) throw new Error("Runtime target escapes the Dragonwilds installation.");
  return target;
}
function removeEmptyParents(file, stop) {
  let current = path.dirname(file);
  const root = path.resolve(stop);
  while (current.toLowerCase().startsWith(root.toLowerCase()) && current !== root) {
    try { if (fs.readdirSync(current).length) break; fs.rmdirSync(current); } catch { break; }
    current = path.dirname(current);
  }
}
function install(worldId, component, zipPath) {
  const kind = String(component || "").trim().toLowerCase();
  if (!COMPONENTS.has(kind)) throw new Error("Runtime component must be UE4SS Server, UE4SS Steam, UE4SS Game Pass, or RuneSchema.");
  const world = dbm.getWorld(worldId);
  if (!world) throw new Error("World not found");
  if (!zipPath || path.extname(zipPath).toLowerCase() !== ".zip" || !fs.existsSync(zipPath)) throw new Error("Choose a readable runtime ZIP.");

  const zip = new AdmZip(zipPath);
  const entries = zip.getEntries().filter((e) => !e.isDirectory);
  if (!entries.length) throw new Error("Runtime ZIP is empty.");
  if (entries.length > 5000) throw new Error("Runtime ZIP contains too many files.");
  const expanded = entries.reduce((sum, e) => sum + Number(e.header?.size || e.getData().length || 0), 0);
  if (expanded > 1024 * 1024 * 1024) throw new Error("Runtime ZIP expands beyond the 1 GiB safety limit.");

  const normalized = stripWrapper(entries.map((e) => safeParts(e.entryName)));
  const root = P.worldRuntimeDir(worldId, kind);
  const candidate = path.join(root, ".candidate-" + crypto.randomBytes(6).toString("hex"));
  fs.mkdirSync(candidate, { recursive: true });
  const records = [];
  try {
    for (let i = 0; i < entries.length; i++) {
      const relativeParts = normalizeRuntimePath(kind, normalized[i]);
      if (!relativeParts) continue;
      const filename = relativeParts[relativeParts.length - 1];
      if (/^rsdragonwilds.*\.exe$/i.test(filename)) throw new Error("Runtime ZIP may not contain a Dragonwilds executable.");
      const relative = relativeParts.join("/");
      const output = localTarget(candidate, relative);
      fs.mkdirSync(path.dirname(output), { recursive: true });
      fs.writeFileSync(output, entries[i].getData());
      records.push({
        relative,
        size: fs.statSync(output).size,
        sha256: sha256File(output),
        clientEligible: kind !== "ue4ss-server",
      });
    }
    if (kind.startsWith("ue4ss-")) {
      const platformDir = kind === "ue4ss-gamepass" ? "wingdk" : "win64";
      if (!records.some((r) => r.relative.toLowerCase() === `binaries/${platformDir}/ue4ss/ue4ss.dll`)) {
        throw new Error("This is not a complete UE4SS ZIP: ue4ss/UE4SS.dll was not found.");
      }
    }
    if (kind === "runeschema" && !records.some((r) => r.relative.toLowerCase() === "binaries/win64/ue4ss/mods/runeschema/dlls/main.dll")) {
      throw new Error("This is not a complete RuneSchema ZIP: dlls/main.dll was not found.");
    }
    if (kind === "runeschema" && !records.some((r) => r.relative.toLowerCase() === "binaries/win64/ue4ss/mods/runeschema/enabled.txt")) {
      const relative = "Binaries/Win64/ue4ss/Mods/RuneSchema/enabled.txt";
      const output = localTarget(candidate, relative);
      fs.mkdirSync(path.dirname(output), { recursive: true });
      fs.writeFileSync(output, "");
      records.push({ relative, size: 0, sha256: sha256File(output), clientEligible: true });
    }

    const gameRoot = serverGameRoot(world.install_dir);
    const deployToHost = kind === "ue4ss-server" || kind === "runeschema";
    const previous = readManifest(worldId, kind);
    const nextSet = new Set(records.map((r) => r.relative.toLowerCase()));
    if (deployToHost) {
      for (const old of previous?.files || []) {
        if (nextSet.has(String(old.relative).toLowerCase())) continue;
        const target = localTarget(gameRoot, old.relative);
        try { if (fs.existsSync(target) && fs.statSync(target).isFile()) fs.unlinkSync(target); removeEmptyParents(target, gameRoot); } catch {}
      }
      for (const record of records) {
        const source = localTarget(candidate, record.relative);
        const target = localTarget(gameRoot, record.relative);
        fs.mkdirSync(path.dirname(target), { recursive: true });
        const temp = target + ".rsdw-runtime";
        fs.copyFileSync(source, temp);
        try {
          fs.renameSync(temp, target);
        } catch {
          fs.rmSync(target, { force: true });
          fs.renameSync(temp, target);
        }
      }
    }

    const permanent = filesRoot(worldId, kind);
    fs.rmSync(permanent, { recursive: true, force: true });
    fs.renameSync(candidate, permanent);
    const meta = {
      schema: "RSDWSync.RuntimePackage.v1",
      component: kind,
      archive: path.basename(zipPath),
      archiveSha256: sha256File(zipPath),
      installedAt: Date.now(),
      files: records,
    };
    fs.writeFileSync(manifestPath(worldId, kind), JSON.stringify(meta, null, 2), "utf8");
    return status(worldId);
  } finally {
    if (fs.existsSync(candidate)) fs.rmSync(candidate, { recursive: true, force: true });
  }
}
function packageStatus(worldId, component) {
  const meta = readManifest(worldId, component);
  if (!meta) return { component, installed: false, files: 0, clientFiles: 0 };
  return {
    component,
    installed: true,
    archive: meta.archive,
    sha256: meta.archiveSha256,
    installedAt: meta.installedAt,
    files: (meta.files || []).length,
    clientFiles: (meta.files || []).filter((f) => f.clientEligible).length,
  };
}
function status(worldId) {
  return {
    ue4ssServer: packageStatus(worldId, "ue4ss-server"),
    ue4ssSteam: packageStatus(worldId, "ue4ss-steam"),
    ue4ssGamepass: packageStatus(worldId, "ue4ss-gamepass"),
    runeschema: packageStatus(worldId, "runeschema"),
  };
}
function syncFiles(worldId, platform = "steam") {
  const selectedPlatform = platform === "gamepass" ? "gamepass" : "steam";
  const out = [];
  const components = selectedPlatform === "gamepass"
    ? ["ue4ss-gamepass", "runeschema"]
    : ["ue4ss-steam", "runeschema"];
  for (const component of components) {
    const meta = readManifest(worldId, component);
    for (const file of meta?.files || []) {
      if (!file.clientEligible) continue;
      const source = localTarget(filesRoot(worldId, component), file.relative);
      if (!fs.existsSync(source)) continue;
      let relative = file.relative.replace(/\\/g, "/");
      if (selectedPlatform === "gamepass" && component === "runeschema") {
        relative = relative.replace(/^Binaries\/Win64\//i, "Binaries/WinGDK/");
      }
      out.push({
        component,
        target: "RSDragonwilds/" + relative,
        size: file.size,
        sha256: file.sha256,
        source,
      });
    }
  }
  return out;
}
function syncUnits(worldId, platform = "steam") {
  const grouped = new Map();
  for (const file of syncFiles(worldId, platform)) {
    if (!grouped.has(file.component)) grouped.set(file.component, []);
    grouped.get(file.component).push(file);
  }
  return [...grouped.entries()].map(([component, files]) => {
    const identity = crypto.createHash("sha256");
    for (const file of files) identity.update(`${file.target}\0${file.size}\0${file.sha256}\n`);
    return {
      key: "runtime:" + component,
      name: component.startsWith("ue4ss-")
        ? `UE4SS Runtime · ${component === "ue4ss-gamepass" ? "PC Game Pass" : component === "ue4ss-server" ? "Dedicated Server" : "Steam"}`
        : "RuneSchema Runtime",
      type: "runtime",
      runtimeComponent: component,
      contentHash: identity.digest("hex"),
      fileCount: files.length,
      bytes: files.reduce((sum, file) => sum + file.size, 0),
      files,
    };
  });
}
function resolveSyncFile(worldId, target, platform = "steam") {
  return syncFiles(worldId, platform).find((file) => file.target === target) || null;
}

module.exports = { install, status, syncFiles, syncUnits, resolveSyncFile };
