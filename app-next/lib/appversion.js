// lib/appversion.js
// Checks GitHub for the latest app release and reports whether a newer version is
// out. The app never self-updates (it ships as a packaged Electron build) — this
// only surfaces "an update is available" so the UI can link to the release.
//
// Shared by the /api/app/version route (serves the cached result) and the
// scheduler's background poller (refreshes it every 30 min so the check happens
// even with no page open).
const https = require("https");
const fs = require("fs");
const path = require("path");

const REPO = "gh0sted5456-us/Dragonwilds-Sync";
const RELEASES_URL = `https://github.com/${REPO}/releases/latest`;
const BRANCHES = { stable: "main", experimental: "codex/super-experimental" };

// How long a fetched release is trusted before we look again. The scheduler polls
// on this cadence; a navigation that lands after it just reuses the cache.
const TTL = 30 * 60 * 1000; // 30 min

const g = globalThis;
if (!g.__APP_APPVER) g.__APP_APPVER = { at: 0, data: null };

// Current app version: injected by Electron (app.getVersion()), else package.json.
function currentVersion() {
  if (process.env.APP_MANAGER_APP_VERSION || process.env.DWSM_APP_VERSION) return process.env.APP_MANAGER_APP_VERSION || process.env.DWSM_APP_VERSION;
  try {
    const pkg = JSON.parse(fs.readFileSync(path.join(process.cwd(), "package.json"), "utf8"));
    return pkg.version || "0.0.0";
  } catch { return "0.0.0"; }
}

function currentBuildInfo() {
  let saved = {};
  try { saved = JSON.parse(fs.readFileSync(path.join(process.cwd(), "build-info.json"), "utf8")); } catch {}
  const version = currentVersion();
  const branch = process.env.APP_MANAGER_BUILD_BRANCH || saved.branch || (version.includes("experimental") ? BRANCHES.experimental : BRANCHES.stable);
  const channel = branch === BRANCHES.experimental || version.includes("experimental") ? "experimental" : "stable";
  return {
    version,
    commit: process.env.APP_MANAGER_BUILD_COMMIT || saved.commit || null,
    branch: BRANCHES[channel],
    channel,
    channelLabel: channel === "experimental" ? "Super Experimental" : "Main",
  };
}

// Compare dotted numeric versions. Returns 1 if a>b, -1 if a<b, 0 if equal.
function cmp(a, b) {
  const pa = String(a).replace(/^v/, "").split(".").map((n) => parseInt(n, 10) || 0);
  const pb = String(b).replace(/^v/, "").split(".").map((n) => parseInt(n, 10) || 0);
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    const d = (pa[i] || 0) - (pb[i] || 0);
    if (d) return d > 0 ? 1 : -1;
  }
  return 0;
}

function getJson(url) {
  return new Promise((resolve, reject) => {
  const req = https.get(url, {
      headers: { "User-Agent": "dwsm-server-manager", Accept: "application/vnd.github+json" },
      timeout: 6000,
    }, (res) => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        res.destroy();
        return getJson(res.headers.location).then(resolve, reject);
      }
      let body = "";
      res.on("data", (c) => (body += c));
      res.on("end", () => {
        if (res.statusCode !== 200) return reject(new Error(`GitHub ${res.statusCode}`));
        try { resolve(JSON.parse(body)); } catch (e) { reject(e); }
      });
    });
    req.on("error", reject);
    req.on("timeout", () => { req.destroy(); reject(new Error("timeout")); });
  });
}

// Fetch the latest release from GitHub and store it in the shared cache. Always
// resolves — on failure it caches a "not checked" marker and shortens the next
// retry to ~5 min instead of holding the failure for the full TTL.
async function refresh(now = Date.now()) {
  const build = currentBuildInfo();
  try {
    const [commitResult, releaseResult] = await Promise.allSettled([
      getJson(`https://api.github.com/repos/${REPO}/commits/${encodeURIComponent(build.branch)}`),
      getJson(`https://api.github.com/repos/${REPO}/releases/latest`),
    ]);
    if (commitResult.status !== "fulfilled" && releaseResult.status !== "fulfilled") throw new Error("GitHub update endpoints unavailable");
    const commit = commitResult.status === "fulfilled" ? commitResult.value : null;
    const rel = releaseResult.status === "fulfilled" ? releaseResult.value : {};
    const latest = (rel.tag_name || "").replace(/^v/, "");
    const assets = (rel.assets || [])
      .filter((a) => /\.(exe|AppImage)$/i.test(a.name))
      .map((a) => ({ name: a.name, url: a.browser_download_url }));
    const branchUrl = `https://github.com/${REPO}/tree/${build.branch}`;
    const data = {
      latest: latest || null,
      latestCommit: commit?.sha || null,
      latestCommitAt: commit?.commit?.committer?.date || null,
      releaseUrl: build.channel === "experimental" ? branchUrl : (rel.html_url || branchUrl),
      branchUrl,
      assets,
      checked: true,
    };
    g.__APP_APPVER = { at: now, data };
    return data;
  } catch {
    const data = { latest: null, latestCommit: null, releaseUrl: `https://github.com/${REPO}/tree/${build.branch}`, assets: [], checked: false };
    g.__APP_APPVER = { at: now - TTL + 5 * 60 * 1000, data };
    return data;
  }
}

// Return the app-version status, refreshing from GitHub if the cache is stale.
// updateAvailable is derived fresh each call so it stays correct even when the app
// version changes without a new fetch.
async function getStatus() {
  const now = Date.now();
  let data = g.__APP_APPVER.data;
  if (!data || now - g.__APP_APPVER.at >= TTL) data = await refresh(now);
  const build = currentBuildInfo();
  const commitUpdate = !!build.commit && !!data.latestCommit && build.commit !== data.latestCommit;
  const releaseUpdate = build.channel === "stable" && !!data.latest && cmp(data.latest, build.version) > 0;
  const updateAvailable = commitUpdate || releaseUpdate;
  return { current: build.version, currentCommit: build.commit, branch: build.branch, channel: build.channel, channelLabel: build.channelLabel, latest: data.latest, latestCommit: data.latestCommit, latestCommitAt: data.latestCommitAt, releaseUrl: data.releaseUrl, branchUrl: data.branchUrl, assets: data.assets, checked: data.checked, updateAvailable };
}

// Refresh only if the cache is older than the TTL. Used by the background poller so
// it never hammers GitHub if a route already refreshed recently.
async function refreshIfStale(now = Date.now()) {
  if (!g.__APP_APPVER.data || now - g.__APP_APPVER.at >= TTL) return refresh(now);
  return g.__APP_APPVER.data;
}

module.exports = { getStatus, refresh, refreshIfStale, currentVersion, currentBuildInfo, cmp, TTL, RELEASES_URL, BRANCHES };
