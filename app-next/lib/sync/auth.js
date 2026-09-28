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

module.exports = { authorizeWorldRequest };
