/*
 * Service worker du tableau de bord Sentinel (application installable).
 *
 * - Pages : réseau d'abord, copie en cache si le réseau est coupé (l'application s'ouvre et affiche
 *   « reconnexion » au lieu d'une page d'erreur du navigateur).
 * - /assets/ : fichiers versionnés par Vite (nom haché), servis depuis le cache une fois téléchargés.
 * - /api et /ws ne passent jamais par le cache : données en direct, sessions, flux caméra.
 *
 * Changer VERSION invalide les copies des pages ; les assets se renouvellent seuls (noms hachés).
 */
const VERSION = "sentinel-v2";
const PAGES = `${VERSION}-pages`;
const ASSETS = "sentinel-assets";
const MAX_ASSETS = 80;
const SHELL = ["/index.html", "/manifest.json", "/icons/icon-192.png", "/icons/apple-touch-icon.png"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(PAGES).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    for (const key of await caches.keys()) if (key !== PAGES && key !== ASSETS) await caches.delete(key);
    await self.clients.claim();
  })());
});

async function trim(cache) {
  const keys = await cache.keys();
  for (let i = 0; i < keys.length - MAX_ASSETS; i++) await cache.delete(keys[i]);
}

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/ws/")) return;

  if (url.pathname.startsWith("/assets/")) {
    event.respondWith((async () => {
      const cache = await caches.open(ASSETS);
      const hit = await cache.match(req);
      if (hit) return hit;
      const res = await fetch(req);
      if (res.ok) { cache.put(req, res.clone()); trim(cache); }
      return res;
    })());
    return;
  }

  if (req.mode === "navigate") {
    event.respondWith((async () => {
      const cache = await caches.open(PAGES);
      try {
        const res = await fetch(req);
        if (res.ok) cache.put(req, res.clone());
        return res;
      } catch {
        return (await cache.match(req)) || (await cache.match("/index.html")) || Response.error();
      }
    })());
  }
});
