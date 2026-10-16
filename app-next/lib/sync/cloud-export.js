// Prepare the exact client-required files for a public folder without changing
// the active delivery mode. Operators upload these files and add provider URLs.
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const { pipeline } = require("stream/promises");
const { P } = require("../paths");
const sync = require("./manifest");
const cloud = require("./cloud-storage");

const jobs = globalThis.__RSDW_CLOUD_EXPORT_JOBS__ || (globalThis.__RSDW_CLOUD_EXPORT_JOBS__ = new Map());

function status(worldId) {
  const job = jobs.get(String(worldId));
  return job ? { ...job } : { phase: "idle", copiedFiles: 0, totalFiles: 0, copiedBytes: 0, totalBytes: 0 };
}

function safeTarget(target) {
  const value = String(target || "").replace(/\\/g, "/");
  const parts = value.split("/");
  if (!value.startsWith("RSDragonwilds/") || parts.some((part) => !part || part === "." || part === ".." || /[<>:"|?*]/.test(part))) {
    throw new Error(`Unsafe cloud export target: ${value}`);
  }
  return parts;
}

async function hashFile(file) {
  const hash = crypto.createHash("sha256");
  for await (const chunk of fs.createReadStream(file)) hash.update(chunk);
  return hash.digest("hex");
}

function start(worldId, { platform = "steam", manifest = null, resolver = sync.resolveWorldFile, fetchManifest = cloud.fetchPublicManifest } = {}) {
  const id = String(worldId || "");
  if (!/^[a-zA-Z0-9_-]{1,120}$/.test(id)) throw new Error("Invalid World ID for export.");
  if (!["steam", "gamepass"].includes(platform)) throw new Error("Choose Steam or Game Pass files.");
  if (jobs.get(id)?.phase === "copying" || jobs.get(id)?.phase === "verifying") return status(id);
  const sourceManifest = manifest || sync.buildWorldManifest(id, { platform });
  const files = (sourceManifest.units || []).flatMap((unit) => unit.files || []);
  if (files.length > 50000) throw new Error("Too many files for cloud export.");
  const seen = new Set();
  for (const file of files) {
    safeTarget(file.target);
    const key = file.target.toLowerCase();
    if (seen.has(key)) throw new Error(`Duplicate cloud export target: ${file.target}`);
    seen.add(key);
  }
  const job = {
    phase: "copying", copiedFiles: 0, totalFiles: files.length, copiedBytes: 0,
    totalBytes: files.reduce((sum, file) => sum + Number(file.size || 0), 0),
    currentFile: "", folder: "", error: "", platform, reusedLinks: 0, missingLinks: 0, warning: "",
  };
  jobs.set(id, job);
  const base = path.join(P.data(), "delivery-exports", id);
  const folder = path.join(base, `${Date.now()}-${String(sourceManifest.revision || "release").slice(0, 12)}`);
  void (async () => {
    try {
      await fs.promises.mkdir(folder, { recursive: true });
      for (const file of files) {
        job.currentFile = file.target;
        const parts = safeTarget(file.target);
        const destination = path.resolve(folder, ...parts);
        if (!destination.toLowerCase().startsWith((path.resolve(folder) + path.sep).toLowerCase())) throw new Error("Export target escaped its folder.");
        const source = resolver(id, file.target, { platform }).source;
        await fs.promises.mkdir(path.dirname(destination), { recursive: true });
        const input = fs.createReadStream(source);
        const output = fs.createWriteStream(destination, { flags: "wx" });
        await pipeline(input, output);
        job.phase = "verifying";
        const copied = await fs.promises.stat(destination);
        if (copied.size !== Number(file.size) || await hashFile(destination) !== String(file.sha256).toLowerCase()) {
          throw new Error(`Export verification failed: ${file.target}`);
        }
        job.copiedFiles += 1;
        job.copiedBytes += copied.size;
        job.phase = "copying";
      }
      // A public folder URL does not expose a reliable per-file link index.
      // Reuse only URLs whose target, size and SHA-256 still match the public
      // manifest (or our last verified cache). Changed/new files need upload
      // and a fresh link before this manifest can be published.
      const config = cloud.getConfig(id);
      let previousFiles = config.cache?.files || [];
      if (config.manifestUrl) {
        try {
          const remote = await fetchManifest(id);
          if (remote.schema !== cloud.SCHEMA || !Array.isArray(remote.files)) throw new Error("The public manifest format is invalid");
          previousFiles = remote.files;
        } catch (error) {
          job.warning = `Could not read the existing public manifest; using cached verified links when available: ${String(error.message || error).replace(/https?:\/\/\S+/gi, "[redacted]")}`;
        }
      }
      const known = new Map();
      for (const item of previousFiles) {
        if (!item?.target || !item?.url) continue;
        try {
          known.set(`${item.target}\0${item.size}\0${String(item.sha256).toLowerCase()}`, cloud.normalizePublicUrl(item.url, config.provider));
        } catch { /* Do not carry forward invalid or wrong-provider links. */ }
      }
      const entries = files.map((file) => {
        const url = known.get(`${file.target}\0${file.size}\0${String(file.sha256).toLowerCase()}`);
        if (url) job.reusedLinks += 1;
        else job.missingLinks += 1;
        return { target: file.target, size: file.size, sha256: file.sha256, url: url || "PASTE_PUBLIC_FILE_LINK" };
      });
      const template = {
        schema: cloud.SCHEMA, revision: sourceManifest.revision,
        files: entries,
      };
      await fs.promises.writeFile(path.join(folder, "rsdw-manifest.json"), JSON.stringify(template, null, 2) + "\n", { flag: "wx" });
      job.folder = folder;
      job.currentFile = "";
      job.phase = "ready";
    } catch (error) {
      job.phase = "failed";
      job.error = error.message || String(error);
    }
  })();
  return status(id);
}

module.exports = { safeTarget, status, start };
