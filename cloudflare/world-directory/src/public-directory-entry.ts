import coreWorker from './index';

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
  }), {
    status: 200,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'cache-control': 'public, max-age=300',
      ...corsHeaders(),
    },
  });
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

    if (request.method === 'GET' && ['/worlds', '/api/worlds', '/manifest'].includes(url.pathname)) {
      url.pathname = '/api/v1/worlds';
      const forwarded = new Request(url.toString(), request);
      return core.fetch(forwarded, env, ctx);
    }

    return core.fetch(request, env, ctx);
  },

  async scheduled(controller: ScheduledController, env: any, ctx: ExecutionContext): Promise<void> {
    if (typeof core.scheduled === 'function') {
      await core.scheduled(controller, env, ctx);
    }
  },
};
