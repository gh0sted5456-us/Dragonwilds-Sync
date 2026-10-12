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

function safeIdentity(value) {
  const clean = String(value || "").replace(/[^a-zA-Z0-9_.-]/g, "_").slice(0, 80);
  return clean || crypto.randomBytes(8).toString("hex");
}

function runtimeIdentity(source) {
  try {
    const info = JSON.parse(fs.readFileSync(path.join(source, "build-info.json"), "utf8"));
    if (info.commit) return safeIdentity(`${info.version || "build"}-${info.commit}`);
  } catch {}
  try { return safeIdentity(fs.readFileSync(path.join(source, ".next", "BUILD_ID"), "utf8").trim()); }
  catch { return safeIdentity(null); }
}

function verifyRuntime(root) {
  const missing = REQUIRED.filter((relative) => !fs.existsSync(path.join(root, relative)));
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
  try {
    materializeTree(source, target);
    verifyRuntime(target);
  } catch (error) {
    fs.rmSync(target, { recursive: true, force: true });
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

module.exports = { materializeRuntime, verifyRuntime, runtimeIdentity, materializeTree, REQUIRED };
