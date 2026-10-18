const crypto = require("crypto");
const { NextResponse } = require("next/server");
const auth = require("./remoteauth");
const jobs = require("./jobs");

function jobsResponse(req) {
  const headers = { "Cache-Control": "no-store, private", "X-Content-Type-Options": "nosniff", Vary: "Cookie" };
  // Logs can contain paths and private data. Authorize before validating a tag.
  if (!auth.requireAdmin(req)) return NextResponse.json({ ok: false, error: "Administrator access required." }, { status: 403, headers });
  // Fingerprint the actual payload, including direct job mutations and retention
  // pruning. No revision counter can accidentally conceal a progress/log change.
  const body = JSON.stringify({ ok: true, jobs: jobs.listJobs() });
  const etag = `"${crypto.createHash("sha256").update(body).digest("hex")}"`;
  headers.ETag = etag;
  const requested = (req.headers.get("if-none-match") || "").split(",");
  if (requested.some((tag) => tag.trim().replace(/^W\//, "") === etag)) return new NextResponse(null, { status: 304, headers });
  return new NextResponse(body, { headers: { ...headers, "Content-Type": "application/json; charset=utf-8" } });
}
module.exports = { jobsResponse };
