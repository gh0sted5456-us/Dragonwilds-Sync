import coreWorker from './index';
import { publicScanStatus, scanPublicSourcesIncrementally } from './rotating-public-scan';

const core = coreWorker as any;

function corsHeaders(): HeadersInit {
  return {
    'access-control-allow-origin': '*',
    'access-control-allow-methods': 'GET, OPTIONS',
    'access-control-allow-headers': 'content-type',
  };
}

function directoryDescriptor(request: Request): Response {
  const base = new URL(request.url);
  base.pathname = '';
  base.search = '';
  base.hash = '';
  const origin = base.toString().replace(/\/$/, '');
  return new Response(JSON.stringify({
    format: 'dragonwilds-sync-public-directory-link',
    version: 1,
    name: 'Dragonwilds Sync Public Server Directory',
    api_base: origin,
    worlds_url: `${origin}/api/v1/worlds`,
    sources_url: `${origin}/api/v1/sources`,
    compatible_aliases: [`${origin}/worlds`, `${origin}/api/worlds`, `${origin}/manifest`],
    read_only: true,
    collection: {
      mode: 'resumable-full-scan',
      refresh: 'incremental-5-minute-cursor',
    },
  }), {
    status: 200,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'cache-control': 'public, max-age=300',
      ...corsHeaders(),
    },
  });
}

function isWorldRead(pathname: string): boolean {
  return ['/api/v1/worlds', '/worlds', '/api/worlds', '/manifest'].includes(pathname);
}

async function sourceResponseWithScanProgress(request: Request, env: any, ctx: ExecutionContext): Promise<Response> {
  ctx.waitUntil(scanPublicSourcesIncrementally(env, false));
  const base = await core.fetch(request, env, ctx);
  if (!base.ok) return base;
  try {
    const payload = await base.clone().json() as Record<string, unknown>;
    const scan = await publicScanStatus(env);
    const headers = new Headers(base.headers);
    headers.set('cache-control', 'public, max-age=30');
    return new Response(JSON.stringify({ ...payload, collection_mode: 'resumable-full-scan', scan }), {
      status: base.status,
      headers,
    });
  } catch {
    return base;
  }
}

export default {
  async fetch(request: Request, env: any, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === 'OPTIONS' && ['/worlds', '/api/worlds', '/manifest', '/directory-source.json'].includes(url.pathname)) {
      return new Response(null, { status: 204, headers: corsHeaders() });
    }

    if (request.method === 'GET' && url.pathname === '/directory-source.json') {
      return directoryDescriptor(request);
    }

    if (request.method === 'GET' && url.pathname === '/api/v1/sources') {
      return sourceResponseWithScanProgress(request, env, ctx);
    }

    if (request.method === 'GET' && isWorldRead(url.pathname)) {
      // Reads never scrape providers in the browser. They may nudge one bounded
      // background scan batch when the persisted scan state is due.
      ctx.waitUntil(scanPublicSourcesIncrementally(env, false));
      if (url.pathname !== '/api/v1/worlds') {
        url.pathname = '/api/v1/worlds';
        const forwarded = new Request(url.toString(), request);
        return core.fetch(forwarded, env, ctx);
      }
    }

    return core.fetch(request, env, ctx);
  },

  async scheduled(_controller: ScheduledController, env: any, ctx: ExecutionContext): Promise<void> {
    // Do not call the older fixed-window source refresher here. This rotating
    // scan keeps a generation/cursor in D1 and retires stale rows only after a
    // complete provider pass, allowing the directory to grow beyond 500 rows.
    ctx.waitUntil(scanPublicSourcesIncrementally(env, true));
  },
};
