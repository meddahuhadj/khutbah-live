/* Service worker minimal : coquille d'application hors-ligne.
   Le temps réel (WebSocket) n'est jamais mis en cache. */
const CACHE = "khutbah-v4";
const SHELL = ["./", "./manifest.webmanifest", "./api/icon-192.png", "./api/icon-512.png",
               "./assets/mosque-bg.jpg"];

self.addEventListener("install", (e) => {
  self.skipWaiting();
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL).catch(() => {})));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  const url = new URL(req.url);
  if (req.method !== "GET") return;
  // Ne jamais intercepter l'API ni les WebSockets.
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/ws/")) return;

  // Navigation : réseau d'abord, cache en secours.
  if (req.mode === "navigate") {
    e.respondWith(
      fetch(req)
        .then((r) => {
          caches.open(CACHE).then((c) => c.put("./", r.clone())).catch(() => {});
          return r;
        })
        .catch(() => caches.match("./"))
    );
    return;
  }
  // Autres GET : cache d'abord.
  e.respondWith(
    caches.match(req).then((hit) => hit || fetch(req).then((r) => {
      if (r.ok && url.origin === location.origin) {
        const copy = r.clone();
        caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => {});
      }
      return r;
    }).catch(() => hit))
  );
});
