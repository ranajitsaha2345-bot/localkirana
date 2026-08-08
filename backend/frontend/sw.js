const CACHE_NAME = "wait-cache-v1";
const FILES_TO_CACHE = [
  "/customer.html",
  "/shopkeeper.html",
  "/manifest.json",
  "/shop-manifest.json",
  "/static/icon-192.png",
  "/static/icon-512.png",
  "/static/shop-icon-192.png",
  "/static/shop-icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(FILES_TO_CACHE))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keyList) =>
      Promise.all(
        keyList.map((key) => {
          if (key !== CACHE_NAME) {
            return caches.delete(key);
          }
        })
      )
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // API calls hamesha fresh network se — kabhi cache mat karo
  if (url.pathname.startsWith("/customer/") || url.pathname.startsWith("/shop/") || url.pathname.startsWith("/api/")) {
    event.respondWith(fetch(event.request));
    return;
  }

  // Static files ke liye cache-first
  event.respondWith(
    caches.match(event.request).then((response) => {
      return response || fetch(event.request);
    })
  );
});