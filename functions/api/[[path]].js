const HOP_BY_HOP_HEADERS = new Set([
  'connection',
  'keep-alive',
  'proxy-authenticate',
  'proxy-authorization',
  'te',
  'trailer',
  'transfer-encoding',
  'upgrade',
]);

function getBackendOrigin(env) {
  return env.API_ORIGIN || env.BACKEND_ORIGIN || '';
}

function cloneHeaders(headers) {
  const cloned = new Headers();

  for (const [key, value] of headers.entries()) {
    const lowerKey = key.toLowerCase();
    if (lowerKey === 'host' || HOP_BY_HOP_HEADERS.has(lowerKey)) continue;
    cloned.set(key, value);
  }

  return cloned;
}

async function proxyRequest(request, env) {
  const origin = getBackendOrigin(env);

  if (!origin) {
    return new Response(
      JSON.stringify({
        error: 'Missing API_ORIGIN or BACKEND_ORIGIN environment variable.',
      }),
      {
        status: 500,
        headers: { 'content-type': 'application/json; charset=utf-8' },
      },
    );
  }

  const incomingUrl = new URL(request.url);
  const targetUrl = new URL(`${incomingUrl.pathname}${incomingUrl.search}`, origin);
  const init = {
    method: request.method,
    headers: cloneHeaders(request.headers),
  };

  if (request.method !== 'GET' && request.method !== 'HEAD') {
    init.body = await request.arrayBuffer();
  }

  const response = await fetch(targetUrl, init);
  const headers = new Headers(response.headers);
  headers.set('access-control-allow-origin', incomingUrl.origin);
  headers.set('access-control-allow-credentials', 'true');

  return new Response(response.body, {
    status: response.status,
    headers,
  });
}

export async function onRequest(context) {
  return proxyRequest(context.request, context.env);
}
