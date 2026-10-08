const crypto = require("crypto");
const dbm = require("../db");

function equal(a, b) {
  const left = Buffer.from(String(a || ""));
  const right = Buffer.from(String(b || ""));
  return left.length === right.length && crypto.timingSafeEqual(left, right);
}

function authorizeWorldRequest(worldId, request) {
  const world = dbm.getWorld(worldId);
  if (!world) return { ok: false, status: 404, error: "World not found" };
  const expected = String(world.server_password || "");
  if (!expected) return { ok: true, world };
  const supplied = request.headers.get("x-rsdw-world-password") || "";
  return equal(expected, supplied)
    ? { ok: true, world }
    : { ok: false, status: 401, error: "The World password is incorrect" };
}

function downloadSecret() {
  let secret = String(dbm.getSetting("sync.downloadSecret", "") || "");
  if (!/^[a-f0-9]{64}$/.test(secret)) {
    secret = crypto.randomBytes(32).toString("hex");
    dbm.setSetting("sync.downloadSecret", secret);
  }
  return secret;
}

function downloadSignature(worldId, target, sha256, expires) {
  return crypto.createHmac("sha256", downloadSecret()).update(`${worldId}\0${target}\0${sha256}\0${expires}`).digest("hex");
}

function signWorldDownload(worldId, target, sha256, expires = Date.now() + 15 * 60 * 1000) {
  return { expires, token: downloadSignature(worldId, target, sha256, expires) };
}

function authorizeWorldDownload(worldId, file, request) {
  const passwordAuth = authorizeWorldRequest(worldId, request);
  if (passwordAuth.ok) return passwordAuth;
  const url = new URL(request.url);
  const expires = Number(url.searchParams.get("expires"));
  const token = url.searchParams.get("token") || "";
  if (!Number.isSafeInteger(expires) || expires < Date.now() || expires > Date.now() + 20 * 60 * 1000) return { ok: false, status: 401, error: "The download link has expired" };
  const expected = downloadSignature(worldId, file.target, file.sha256, expires);
  return equal(expected, token) ? { ok: true, world: passwordAuth.world } : { ok: false, status: 401, error: "The download link is invalid" };
}

module.exports = { authorizeWorldRequest, authorizeWorldDownload, signWorldDownload };
