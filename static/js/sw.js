/**
 * Service Worker — Disaster Response System
 * Strategy:
 *   - App shell (HTML, CSS, JS, fonts) : Cache-First
 *   - API calls (/api/*)               : Network-First with cache fallback
 *   - Navigation (pages)               : Network-First with offline fallback
 *   - SOS submissions (POST /sos)      : Queue via Background Sync
 */

const CACHE_VERSION   = 'v1';
const SHELL_CACHE     = `drs-shell-${CACHE_VERSION}`;
const DATA_CACHE      = `drs-data-${CACHE_VERSION}`;
const OFFLINE_PAGE    = '/offline';

// ── Assets to precache on install ────────────────────────────────────────────
const SHELL_ASSETS = [
  '/',
  '/dashboard',
  '/offline',
  '/static/css/style.css',
  '/static/js/alert_sound.js',
  '/static/sounds/sos_alarm.mp3',
  '/static/sounds/emergency_alert.mp3',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js',
  'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css',
];

// ── API routes to cache for offline reading ───────────────────────────────────
const CACHEABLE_API = [
  '/api/stats',
  '/api/alerts/latest',
  '/api/reports/recent',
  '/api/sos/count',
  '/api/analytics/summary',
];

// ── Install ───────────────────────────────────────────────────────────────────
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(SHELL_CACHE).then(cache => {
      // Cache shell assets; ignore failures for CDN items if offline
      return Promise.allSettled(
        SHELL_ASSETS.map(url => cache.add(url).catch(() => {}))
      );
    }).then(() => self.skipWaiting())
  );
});

// ── Activate — purge old caches ───────────────────────────────────────────────
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys
          .filter(k => k !== SHELL_CACHE && k !== DATA_CACHE)
          .map(k => caches.delete(k))
      )
    ).then(() => self.clients.claim())
  );
});

// ── Fetch ─────────────────────────────────────────────────────────────────────
self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip non-GET entirely for caching (POST handled by Background Sync)
  if (request.method !== 'GET') return;

  // Skip chrome-extension and non-http(s)
  if (!url.protocol.startsWith('http')) return;

  // ── API routes: Network-First, cache on success ───────────────────────────
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(networkFirstWithCache(request, DATA_CACHE));
    return;
  }

  // ── Static assets: Cache-First ────────────────────────────────────────────
  if (
    url.pathname.startsWith('/static/') ||
    url.hostname.includes('cdn.jsdelivr.net') ||
    url.hostname.includes('fonts.googleapis.com') ||
    url.hostname.includes('fonts.gstatic.com')
  ) {
    event.respondWith(cacheFirst(request, SHELL_CACHE));
    return;
  }

  // ── HTML navigation: Network-First, offline page fallback ────────────────
  if (request.mode === 'navigate' || request.headers.get('Accept')?.includes('text/html')) {
    event.respondWith(networkFirstWithOfflineFallback(request));
    return;
  }

  // Everything else: Network-First
  event.respondWith(networkFirstWithCache(request, DATA_CACHE));
});

// ── Background Sync — offline SOS queue ──────────────────────────────────────
self.addEventListener('sync', event => {
  if (event.tag === 'sync-sos') {
    event.waitUntil(flushSOSQueue());
  }
  if (event.tag === 'sync-reports') {
    event.waitUntil(flushReportQueue());
  }
});

async function flushSOSQueue() {
  const db    = await openIDB();
  const items = await getAllFromStore(db, 'sos_queue');
  for (const item of items) {
    try {
      const resp = await fetch('/sos', {
        method:  'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body:    item.formData,
      });
      if (resp.ok) {
        await deleteFromStore(db, 'sos_queue', item.id);
        // Notify open windows
        self.clients.matchAll().then(clients =>
          clients.forEach(c => c.postMessage({ type: 'SOS_SYNCED', id: item.id }))
        );
      }
    } catch (e) {
      // Still offline — leave in queue
    }
  }
}

async function flushReportQueue() {
  const db    = await openIDB();
  const items = await getAllFromStore(db, 'report_queue');
  for (const item of items) {
    try {
      const resp = await fetch('/reports/new', {
        method:  'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body:    item.formData,
      });
      if (resp.ok) {
        await deleteFromStore(db, 'report_queue', item.id);
        self.clients.matchAll().then(clients =>
          clients.forEach(c => c.postMessage({ type: 'REPORT_SYNCED', id: item.id }))
        );
      }
    } catch (e) {}
  }
}

// ── Push notifications ────────────────────────────────────────────────────────
self.addEventListener('push', event => {
  const data = event.data?.json() || {};
  event.waitUntil(
    self.registration.showNotification(data.title || '🚨 Disaster Alert', {
      body:    data.body || 'A new emergency alert has been issued.',
      icon:    '/static/icons/icon-192.png',
      badge:   '/static/icons/icon-72.png',
      tag:     'disaster-alert',
      vibrate: [200, 100, 200, 100, 400],
      data:    { url: data.url || '/alerts' },
      actions: [
        { action: 'view',    title: 'View Alert' },
        { action: 'dismiss', title: 'Dismiss'    },
      ],
    })
  );
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  if (event.action !== 'dismiss') {
    event.waitUntil(
      self.clients.openWindow(event.notification.data?.url || '/alerts')
    );
  }
});

// ── Fetch strategy helpers ────────────────────────────────────────────────────
async function cacheFirst(request, cacheName) {
  const cached = await caches.match(request);
  if (cached) return cached;
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(cacheName);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    return new Response('Offline', { status: 503 });
  }
}

async function networkFirstWithCache(request, cacheName) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(cacheName);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await caches.match(request);
    if (cached) return cached;
    // For API calls return a JSON offline indicator
    if (request.url.includes('/api/')) {
      return new Response(
        JSON.stringify({ offline: true, error: 'You are offline. Showing cached data.' }),
        { headers: { 'Content-Type': 'application/json' }, status: 200 }
      );
    }
    return new Response('Offline', { status: 503 });
  }
}

async function networkFirstWithOfflineFallback(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(SHELL_CACHE);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await caches.match(request);
    if (cached) return cached;
    // Return the offline page
    return caches.match(OFFLINE_PAGE) || new Response(
      '<h1>You are offline</h1><p>Please check your connection.</p>',
      { headers: { 'Content-Type': 'text/html' }, status: 503 }
    );
  }
}

// ── IndexedDB helpers (for offline queue) ────────────────────────────────────
function openIDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open('drs_offline', 1);
    req.onupgradeneeded = e => {
      const db = e.target.result;
      if (!db.objectStoreNames.contains('sos_queue')) {
        db.createObjectStore('sos_queue', { keyPath: 'id', autoIncrement: true });
      }
      if (!db.objectStoreNames.contains('report_queue')) {
        db.createObjectStore('report_queue', { keyPath: 'id', autoIncrement: true });
      }
    };
    req.onsuccess = e => resolve(e.target.result);
    req.onerror   = e => reject(e.target.error);
  });
}

function getAllFromStore(db, storeName) {
  return new Promise((resolve, reject) => {
    const tx  = db.transaction(storeName, 'readonly');
    const req = tx.objectStore(storeName).getAll();
    req.onsuccess = e => resolve(e.target.result);
    req.onerror   = e => reject(e.target.error);
  });
}

function deleteFromStore(db, storeName, id) {
  return new Promise((resolve, reject) => {
    const tx  = db.transaction(storeName, 'readwrite');
    const req = tx.objectStore(storeName).delete(id);
    req.onsuccess = () => resolve();
    req.onerror   = e => reject(e.target.error);
  });
}
