const CACHE_NAME = 'euskal-ageria-kimua-v13';
const STATIC_ASSETS = [
  '/static/manifest.webmanifest',
  '/static/icons/kimua-180.png',
  '/static/icons/kimua-192.png',
  '/static/icons/kimua-512.png'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;

  // Irakasleen datu dinamikoa ez da cacheatzen.
  if (
    url.pathname === '/static/manifest.webmanifest' ||
    url.pathname.startsWith('/static/icons/')
  ) {
    event.respondWith(
      caches.match(event.request).then((cached) => cached || fetch(event.request))
    );
  }
});
