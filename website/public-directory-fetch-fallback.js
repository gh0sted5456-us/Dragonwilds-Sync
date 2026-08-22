/* Resilient Public Server Directory transport.
   Loaded before script.js so the canonical live API remains first choice, while
   an empty/unreachable Worker response transparently falls back to the latest
   same-origin GitHub Pages snapshot. This affects public discovery only. */
(() => {
  const LIVE_HOST = 'dragonwilds-sync-directory.dragonwilds.workers.dev';
  const LIVE_PATH = '/api/v1/worlds';
  const FALLBACK_URL = 'assets/public-worlds-fallback.json';
  const SNAPSHOT_CACHE_MS = 5 * 60 * 1000;
  const originalFetch = window.fetch.bind(window);
  let cachedSnapshot = null;
  let cachedSnapshotAt = 0;
  let snapshotRequest = null;

  function publishDirectoryMeta(payload, transport) {
    const directory = payload?.directory && typeof payload.directory === 'object'
      ? payload.directory
      : {};
    const meta = { ...directory, transport };
    window.__DWS_DIRECTORY_META__ = meta;
    window.dispatchEvent(new CustomEvent('dws-directory-meta', { detail: meta }));
  }

  function isWorldDirectoryRequest(input) {
    try {
      const raw = input instanceof Request ? input.url : String(input || '');
      const url = new URL(raw, window.location.href);
      return url.hostname.toLowerCase() === LIVE_HOST && url.pathname === LIVE_PATH;
    } catch (_) {
      return false;
    }
  }

  async function loadSnapshot() {
    if (cachedSnapshot && Date.now() - cachedSnapshotAt < SNAPSHOT_CACHE_MS) return cachedSnapshot;
    if (snapshotRequest) return snapshotRequest;
    snapshotRequest = (async () => {
      const response = await originalFetch(FALLBACK_URL, {
        headers: { Accept: 'application/json' },
        cache: 'no-store'
      });
      if (!response.ok) throw new Error(`Public snapshot returned HTTP ${response.status}`);
      const payload = await response.json();
      const worlds = Array.isArray(payload?.worlds) ? payload.worlds : [];
      if (!worlds.length) throw new Error('Public snapshot contains no Worlds');
      cachedSnapshot = payload;
      cachedSnapshotAt = Date.now();
      return payload;
    })();
    try {
      return await snapshotRequest;
    } finally {
      snapshotRequest = null;
    }
  }

  function worldKey(world, index, source) {
    const id = String(world?.world_id ?? world?.id ?? '').trim();
    return id || `${source}-${index}`;
  }

  function jsonResponse(payload, source) {
    return new Response(JSON.stringify(payload), {
      status: 200,
      headers: {
        'content-type': 'application/json; charset=utf-8',
        'cache-control': 'no-store',
        'x-dragonwilds-directory-source': source
      }
    });
  }

  async function fallbackResponse() {
    const payload = await loadSnapshot();
    const enriched = {
      ...payload,
      directory: {
        ...(payload?.directory || {}),
        transport: 'github-pages-fallback',
        live_api_attempted: true
      }
    };
    publishDirectoryMeta(enriched, 'github-pages-fallback');
    return jsonResponse(enriched, 'github-pages-fallback');
  }

  async function combinedResponse(livePayload) {
    const snapshot = await loadSnapshot();
    const liveWorlds = Array.isArray(livePayload?.worlds) ? livePayload.worlds : [];
    const snapshotWorlds = Array.isArray(snapshot?.worlds) ? snapshot.worlds : [];
    const merged = new Map();
    snapshotWorlds.forEach((world, index) => merged.set(worldKey(world, index, 'snapshot'), world));
    liveWorlds.forEach((world, index) => merged.set(worldKey(world, index, 'live'), world));
    const enriched = {
      ...snapshot,
      ...livePayload,
      worlds: [...merged.values()],
      directory: {
        ...(snapshot?.directory || {}),
        ...(livePayload?.directory || {}),
        transport: 'cloudflare-live+github-pages-snapshot',
        live_worlds: liveWorlds.length,
        snapshot_worlds: snapshotWorlds.length
      }
    };
    publishDirectoryMeta(enriched, 'cloudflare-live+github-pages-snapshot');
    return jsonResponse(enriched, 'cloudflare-live+github-pages-snapshot');
  }

  window.fetch = async function resilientDirectoryFetch(input, init) {
    if (!isWorldDirectoryRequest(input)) return originalFetch(input, init);

    let liveResponse = null;
    let liveError = null;
    try {
      liveResponse = await originalFetch(input, init);
      if (liveResponse.ok) {
        try {
          const payload = await liveResponse.clone().json();
          if (Array.isArray(payload?.worlds) && payload.worlds.length) {
            try {
              return await combinedResponse(payload);
            } catch (_) {
              publishDirectoryMeta(payload, 'cloudflare-live');
              return liveResponse;
            }
          }
        } catch (_) {
          // Invalid live JSON is treated like an unavailable live directory.
        }
      }
    } catch (error) {
      liveError = error;
    }

    try {
      return await fallbackResponse();
    } catch (fallbackError) {
      if (liveResponse) return liveResponse;
      throw liveError || fallbackError;
    }
  };
})();
