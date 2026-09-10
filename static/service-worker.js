const VERSION = 'v23';
const SHELL_CACHE = `euskal-ageria-shell-${VERSION}`;
const ASSET_CACHE = `euskal-ageria-assets-${VERSION}`;

const SHELL_ASSETS = [
  '/irakasle',
  '/static/manifest.webmanifest',
  '/static/icons/kimua-180.png',
  '/static/icons/kimua-192.png',
  '/static/icons/kimua-512.png'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE).then((cache) => cache.addAll(SHELL_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => ![SHELL_CACHE, ASSET_CACHE].includes(key))
          .map((key) => caches.delete(key))
      )
    )
  );
  self.clients.claim();
});

async function staleWhileRevalidate(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);

  const networkPromise = fetch(request).then((response) => {
    if (response && (response.ok || response.type === 'opaque')) {
      cache.put(request, response.clone()).catch(() => {});
    }
    return response;
  }).catch(() => null);

  return cached || (await networkPromise) || Response.error();
}

async function cacheFirst(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  if (cached) return cached;

  const response = await fetch(request);
  if (response && (response.ok || response.type === 'opaque')) {
    cache.put(request, response.clone()).catch(() => {});
  }
  return response;
}

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;

  const url = new URL(event.request.url);

  // Hasierako panela datu-base gabekoa da:
  // cachetik berehala erakutsi eta atzean eguneratzen da.
  if (
    event.request.mode === 'navigate' &&
    url.origin === self.location.origin &&
    (url.pathname === '/irakasle' || url.pathname === '/irakasle/')
  ) {
    event.respondWith(staleWhileRevalidate(event.request, SHELL_CACHE));
    return;
  }

  // Irakasleen thumbnailak eta PWA ikonoak: cache azkarra + eguneraketa atzean.
  if (
    url.origin === self.location.origin &&
    (
      url.pathname.startsWith('/static/photos_thumb/') ||
      url.pathname.startsWith('/static/icons/') ||
      url.pathname === '/static/manifest.webmanifest'
    )
  ) {
    event.respondWith(staleWhileRevalidate(event.request, ASSET_CACHE));
    return;
  }

  // Tailwind eta Nunito: lehen kargaren ondoren ez joan berriz Internetera.
  if (
    url.hostname === 'cdn.tailwindcss.com' ||
    url.hostname === 'fonts.googleapis.com' ||
    url.hostname === 'fonts.gstatic.com'
  ) {
    event.respondWith(cacheFirst(event.request, ASSET_CACHE));
    return;
  }

  // Gela, maila, historikoa eta puntu aldaketak:
  // EZ cacheatu. Datuak beti zerbitzaritik fresko.
});
