const CACHE_NAME = 'bitassistant-v1';
const urlsToCache = [
  '/',
  '/dashboard.html',
  '/account.html',
  '/profile.html',
  '/upgrade.html',
  '/index.html',
  '/icons/ai.jpg'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(urlsToCache))
  );
});

self.addEventListener('fetch', event => {
  event.respondWith(
    caches.match(event.request)
      .then(response => response || fetch(event.request))
  );
});
