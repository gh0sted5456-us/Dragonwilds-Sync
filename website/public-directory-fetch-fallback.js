/* Resilient Public Server Directory transport.
   Loaded before script.js so the canonical live API remains first choice, while
   an empty/unreachable Worker response transparently falls back to the latest
   same-origin GitHub Pages snapshot. This affects public discovery only. */
(() => {
  const LIVE_HOST = 'dragonwilds-sync-directory.dragonwilds.workers.dev';
  const LIVE_PATH = '/api/v1/worlds';
  const FALLBACK_URL = 'assets/public-worlds-fallback.json';
  const originalFetch = window.fetch.bind(window);

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

  async function fallbackResponse() {
    const response = await originalFetch(FALLBACK_URL, {
      headers: { Accept: 'application/json' },
      cache: 'no-store'
    });
    if (!response.ok) throw new Error(`Public snapshot returned HTTP ${response.status}`);
    const payload = await response.json();
    const worlds = Array.isArray(payload?.worlds) ? payload.worlds : [];
    if (!worlds.length) throw new Error('Public snapshot contains no Worlds');
    const enriched = {
      ...payload,
      directory: {
        ...(payload?.directory || {}),
        transport: 'github-pages-fallback',
        live_api_attempted: true
      }
    };
    publishDirectoryMeta(enriched, 'github-pages-fallback');
    return new Response(JSON.stringify(enriched), {
      status: 200,
      headers: {
        'content-type': 'application/json; charset=utf-8',
        'cache-control': 'no-store',
        'x-dragonwilds-directory-source': 'github-pages-fallback'
      }
    });
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
            publishDirectoryMeta(payload, 'cloudflare-live');
            return liveResponse;
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
