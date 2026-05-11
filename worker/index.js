/**
 * Field Notes sync — Cloudflare Worker
 *
 * A tiny KV-backed REST API that stores your progress JSON keyed by a secret code.
 * Deploy with `wrangler deploy` (see README in /worker).
 *
 * Endpoints:
 *   GET    /state?code=XXX  → returns the JSON blob for that code, or {} if not found
 *   PUT    /state?code=XXX  → body is JSON, stored under that code
 *   DELETE /state?code=XXX  → deletes the blob (used by "Reset everything")
 *
 * Security model:
 *   - The "code" is a shared secret between your devices. Pick something long.
 *   - Anyone with the code can read/write the corresponding state.
 *   - No PII goes into the worker — just completion flags, notes, quiz scores.
 *   - CORS is open (*) so the GitHub Pages site can call it from any origin.
 *   - Codes are normalized (trimmed, lower-cased) and length-checked.
 */

const MIN_CODE_LEN = 8;
const MAX_BODY_BYTES = 256 * 1024; // 256 KB — plenty of room for years of notes

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, PUT, DELETE, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
  'Access-Control-Max-Age': '86400',
};

function jsonResponse(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { 'Content-Type': 'application/json', ...CORS },
  });
}

function normalizeCode(raw) {
  return (raw || '').trim().toLowerCase();
}

export default {
  async fetch(request, env) {
    // CORS preflight
    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: CORS });
    }

    const url = new URL(request.url);
    if (url.pathname !== '/state') {
      return jsonResponse({ error: 'not found' }, 404);
    }

    const code = normalizeCode(url.searchParams.get('code'));
    if (!code || code.length < MIN_CODE_LEN) {
      return jsonResponse({ error: `code must be at least ${MIN_CODE_LEN} characters` }, 400);
    }
    const key = `state:${code}`;

    if (request.method === 'GET') {
      const value = await env.STATE_KV.get(key);
      if (!value) return jsonResponse({}, 200);
      try {
        return jsonResponse(JSON.parse(value), 200);
      } catch (e) {
        return jsonResponse({ error: 'corrupted state' }, 500);
      }
    }

    if (request.method === 'PUT') {
      const body = await request.text();
      if (body.length > MAX_BODY_BYTES) {
        return jsonResponse({ error: 'body too large' }, 413);
      }
      // Validate it's JSON before storing
      try { JSON.parse(body); }
      catch (e) { return jsonResponse({ error: 'invalid json' }, 400); }
      await env.STATE_KV.put(key, body);
      return jsonResponse({ ok: true, bytes: body.length }, 200);
    }

    if (request.method === 'DELETE') {
      await env.STATE_KV.delete(key);
      return jsonResponse({ ok: true }, 200);
    }

    return jsonResponse({ error: 'method not allowed' }, 405);
  },
};
