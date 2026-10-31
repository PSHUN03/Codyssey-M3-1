/* 서비스 워커 — 정적 파일은 캐시로 즉시 응답하면서 백그라운드에서 갱신(stale-while-revalidate),
   화면은 네트워크 우선(오프라인이면 안내). API는 캐시하지 않는다.
   CSS·JS 주소에는 배포마다 바뀌는 ?v= 버전이 붙어 있어 수정 사항이 바로 반영된다. */
const CACHE = "sadari-v3";
const ASSETS = ["/static/css/app.css", "/static/js/app.js", "/static/icons/icon-192.png", "/static/icons/favicon.svg"];
const OFFLINE_HTML = `<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>오프라인</title><body style="font-family:sans-serif;padding:40px;text-align:center;background:#e8ebe6;color:#0e0f0c">
<h1>인터넷 연결이 끊겼어요</h1><p>연결되면 다시 시도해 주세요.</p></body>`;

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(ASSETS)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  const url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== location.origin) return;
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/internal/")) return;

  if (url.pathname.startsWith("/static/")) {
    event.respondWith(
      caches.open(CACHE).then(async (cache) => {
        const hit = await cache.match(req);
        const refresh = fetch(req).then((res) => {
          if (res.ok) cache.put(req, res.clone());
          return res;
        });
        return hit || refresh;
      })
    );
    return;
  }
  if (req.mode === "navigate") {
    event.respondWith(
      fetch(req).catch(() => new Response(OFFLINE_HTML, { headers: { "Content-Type": "text/html; charset=utf-8" } }))
    );
  }
});
