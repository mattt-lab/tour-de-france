// CORS relay for ASO's live race telemetry API (racecenter.letour.fr).
// That endpoint has no Access-Control-Allow-Origin header, so the
// dashboard's browser-side JS can't fetch it directly — this Worker just
// forwards any path under it to the real API and adds CORS, so the
// client can poll it every ~10s for the in-race live tracker instead of
// going through the 10-minute GitHub Actions cron used for everything
// else on the site.
//
// Deploy (one-time, manual — needs your own Cloudflare account):
//   1. Sign up free at https://dash.cloudflare.com (no credit card needed).
//   2. Workers & Pages → Create → Create Worker.
//   3. Paste this file's contents into the editor, replacing the default.
//   4. Deploy. Copy the resulting *.workers.dev URL.
//   5. Paste that URL into the TDF_PROXY constant in tdf-dashboard.html.
//
// No API key or secret is needed — the ASO endpoint itself requires no
// auth, and this Worker doesn't either.

export default {
  async fetch(request) {
    const path = new URL(request.url).pathname.replace(/^\//, '');
    if (!path) return new Response('Missing path', { status: 400 });

    const upstream = await fetch(`https://racecenter.letour.fr/api/${path}`, {
      headers: { 'User-Agent': 'Mozilla/5.0' },
    });

    return new Response(upstream.body, {
      status: upstream.status,
      headers: {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Cache-Control': 'public, max-age=15',
      },
    });
  },
};
