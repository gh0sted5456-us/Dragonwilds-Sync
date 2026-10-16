const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

const REQUIRED = [
  "server.js",
  path.join(".next", "BUILD_ID"),
  path.join(".next", "server", "pages", "_error.js"),
  path.join(".next", "server", "app", "api", "app", "instance", "route.js"),
  path.join(".next", "server", "app", "api", "socials", "mods", "route.js"),
];

function runtimeDistDir(root) {
  try {
    const info = JSON.parse(fs.readFileSync(path.join(root, "build-info.json"), "utf8"));
    const candidate = String(info.nextDistDir || ".next").replace(/^\.\//, "");
    if (/^\.next(?:-[a-z0-9-]+)?$/i.test(candidate)) return candidate;
  } catch {}
  return ".next";
}

function requiredFiles(root) {
  const dist = runtimeDistDir(root);
  return REQUIRED.map((relative) => relative.startsWith(`.next${path.sep}`)
    ? path.join(dist, relative.slice(6))
    : relative);
}

function safeIdentity(value) {
  const clean = String(value || "").replace(/[^a-zA-Z0-9_.-]/g, "_").slice(0, 80);
  return clean || crypto.randomBytes(8).toString("hex");
}

function runtimeIdentity(source) {
  let buildId = "";
  try { buildId = fs.readFileSync(path.join(source, runtimeDistDir(source), "BUILD_ID"), "utf8").trim(); } catch {}
  try {
    const info = JSON.parse(fs.readFileSync(path.join(source, "build-info.json"), "utf8"));
    if (info.commit && buildId) {
      // Rebuilding an uncommitted checkout must not reuse its earlier UI cache.
      const digest = crypto.createHash("sha256").update(`${info.version}:${info.commit}:${buildId}`).digest("hex").slice(0, 16);
      return safeIdentity(`${info.version || "build"}-${digest}`);
    }
  } catch {}
  return safeIdentity(buildId || null);
}

function materializeRuntimeAsync(source, dataDirectory) {
  const { Worker } = require("worker_threads");
  return new Promise((resolve, reject) => {
    const worker = new Worker(path.join(__dirname, "runtime-worker.js"), { workerData: { source, dataDirectory } });
    let reported = false;
    worker.once("message", (result) => {
      reported = true;
      if (result.error) reject(new Error(result.error));
      else resolve(result.root);
    });
    worker.once("error", reject);
    worker.once("exit", (code) => { if (!reported) reject(new Error(`Interface staging worker exited before reporting its result (code ${code})`)); });
  });
}

function verifyRuntime(root) {
  const missing = requiredFiles(root).filter((relative) => !fs.existsSync(path.join(root, relative)));
  if (missing.length) throw new Error(`Interface runtime is incomplete: ${missing.join(", ")}`);
  return true;
}

function materializeTree(source, destination) {
  fs.mkdirSync(destination, { recursive: true });
  for (const entry of fs.readdirSync(source, { withFileTypes: true })) {
    const from = path.join(source, entry.name);
    const to = path.join(destination, entry.name);
    if (entry.isDirectory()) materializeTree(from, to);
    else if (entry.isSymbolicLink()) {
      // Packaged Windows builds normally contain no symlinks. Copying the
      // resolved file keeps the cache self-contained when one is encountered.
      fs.copyFileSync(from, to);
    } else if (entry.isFile()) {
      // Portable extraction and AppData normally share the same volume. Hard
      // links make the first launch fast and remain valid after Temp cleanup.
      try { fs.linkSync(from, to); }
      catch { fs.copyFileSync(from, to); }
    }
  }
}

function materializeRuntime(source, dataDirectory) {
  verifyRuntime(source);
  const runtimeRoot = path.join(dataDirectory, "interface-runtime");
  const identity = runtimeIdentity(source);
  const target = path.join(runtimeRoot, identity);
  if (fs.existsSync(target)) {
    try { verifyRuntime(target); return target; }
    catch { fs.rmSync(target, { recursive: true, force: true }); }
  }

  fs.mkdirSync(runtimeRoot, { recursive: true });
  const staged = path.join(runtimeRoot, `${identity}.staging-${crypto.randomUUID()}`);
  try {
    // Publishing a complete tree in one rename also makes quitting during the
    // background copy safe: a partial staging directory is never a warm cache.
    materializeTree(source, staged);
    verifyRuntime(staged);
    fs.renameSync(staged, target);
  } catch (error) {
    fs.rmSync(staged, { recursive: true, force: true });
    throw error;
  }

  // A portable release only needs its current 35–40 MB interface runtime. Old
  // versions are safe to remove after the new copy has been verified and moved.
  for (const entry of fs.readdirSync(runtimeRoot, { withFileTypes: true })) {
    if (!entry.isDirectory() || entry.name === identity) continue;
    fs.rmSync(path.join(runtimeRoot, entry.name), { recursive: true, force: true });
  }
  return target;
}

module.exports = { materializeRuntime, materializeRuntimeAsync, verifyRuntime, runtimeIdentity, runtimeDistDir, materializeTree, REQUIRED };
