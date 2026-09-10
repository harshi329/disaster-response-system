/**
 * Offline Manager — runs on every page
 * - Registers the Service Worker
 * - Shows/hides the offline banner
 * - Intercepts SOS & Report form submissions when offline → queues in IndexedDB
 * - Listens for SW sync messages and notifies user
 */

// ── Register Service Worker ───────────────────────────────────────────────────
if ('serviceWorker' in navigator) {
  window.addEventListener('load', async () => {
    try {
      const reg = await navigator.serviceWorker.register('/static/js/sw.js', { scope: '/' });
      console.log('[SW] Registered, scope:', reg.scope);
    } catch (err) {
      console.warn('[SW] Registration failed:', err);
    }
  });

  // Listen for sync confirmation messages from SW
  navigator.serviceWorker.addEventListener('message', event => {
    const { type } = event.data || {};
    if (type === 'SOS_SYNCED') {
      showToast('✅ Your offline SOS alert has been sent!', 'success');
    }
    if (type === 'REPORT_SYNCED') {
      showToast('✅ Your offline report has been submitted!', 'success');
    }
  });
}

// ── Online / Offline banner ───────────────────────────────────────────────────
function createBanner() {
  const el = document.createElement('div');
  el.id = 'offline-banner';
  el.innerHTML = `
    <i class="bi bi-wifi-off me-2"></i>
    <strong>You are offline.</strong>
    SOS alerts and reports will be queued and sent automatically when you reconnect.
  `;
  Object.assign(el.style, {
    display:         'none',
    position:        'fixed',
    top:             '0',
    left:            '0',
    right:           '0',
    zIndex:          '99999',
    background:      '#dc3545',
    color:           '#fff',
    padding:         '10px 16px',
    textAlign:       'center',
    fontSize:        '.9rem',
    boxShadow:       '0 2px 8px rgba(0,0,0,.3)',
  });
  document.body.prepend(el);
  return el;
}

function createOnlineToast() {
  const el = document.createElement('div');
  el.id = 'online-toast';
  el.innerHTML = `<i class="bi bi-wifi me-2"></i><strong>Back online!</strong> Syncing queued data…`;
  Object.assign(el.style, {
    display:       'none',
    position:      'fixed',
    top:           '12px',
    left:          '50%',
    transform:     'translateX(-50%)',
    zIndex:        '99999',
    background:    '#198754',
    color:         '#fff',
    padding:       '10px 24px',
    borderRadius:  '8px',
    fontSize:      '.9rem',
    boxShadow:     '0 4px 16px rgba(0,0,0,.25)',
  });
  document.body.prepend(el);
  return el;
}

const banner      = createBanner();
const onlineToast = createOnlineToast();

function updateOnlineStatus() {
  if (navigator.onLine) {
    banner.style.display = 'none';
    onlineToast.style.display = 'block';
    setTimeout(() => { onlineToast.style.display = 'none'; }, 3000);
    // Trigger background sync
    if ('serviceWorker' in navigator && 'SyncManager' in window) {
      navigator.serviceWorker.ready.then(reg => {
        reg.sync.register('sync-sos').catch(() => {});
        reg.sync.register('sync-reports').catch(() => {});
      });
    }
  } else {
    banner.style.display = 'block';
    onlineToast.style.display = 'none';
  }
}

window.addEventListener('online',  updateOnlineStatus);
window.addEventListener('offline', updateOnlineStatus);
// Check immediately on load
document.addEventListener('DOMContentLoaded', () => {
  if (!navigator.onLine) banner.style.display = 'block';
});

// ── Intercept SOS form submission when offline ────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  // SOS form
  const sosForm = document.getElementById('sos-form');
  if (sosForm) {
    sosForm.addEventListener('submit', async function (e) {
      if (!navigator.onLine) {
        e.preventDefault();
        const formData = new URLSearchParams(new FormData(this)).toString();
        await queueOfflineItem('sos_queue', formData);
        showToast(
          '🆘 You are offline. Your SOS has been saved and will be sent when you reconnect.',
          'warning',
          6000
        );
        // Still play the siren locally
        if (typeof sosAlarm === 'function') sosAlarm(3);
      }
    });
  }

  // Report form
  const reportForm = document.getElementById('report-form');
  if (reportForm) {
    reportForm.addEventListener('submit', async function (e) {
      if (!navigator.onLine) {
        e.preventDefault();
        const formData = new URLSearchParams(new FormData(this)).toString();
        await queueOfflineItem('report_queue', formData);
        showToast(
          '📋 You are offline. Your report has been saved and will be submitted when you reconnect.',
          'warning',
          6000
        );
      }
    });
  }
});

// ── Queue item in IndexedDB ───────────────────────────────────────────────────
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

async function queueOfflineItem(storeName, formData) {
  try {
    const db = await openIDB();
    return new Promise((resolve, reject) => {
      const tx  = db.transaction(storeName, 'readwrite');
      const req = tx.objectStore(storeName).add({
        formData,
        queuedAt: new Date().toISOString(),
      });
      req.onsuccess = () => resolve();
      req.onerror   = e => reject(e.target.error);
    });
  } catch (err) {
    console.warn('[Offline] Could not queue item:', err);
  }
}

// ── Toast helper ──────────────────────────────────────────────────────────────
function showToast(message, type = 'info', duration = 4000) {
  // Remove existing toast
  const existing = document.getElementById('drs-toast');
  if (existing) existing.remove();

  const colors = { success: '#198754', warning: '#fd7e14', danger: '#dc3545', info: '#0dcaf0' };

  const el = document.createElement('div');
  el.id = 'drs-toast';
  el.innerHTML = message;
  Object.assign(el.style, {
    position:     'fixed',
    bottom:       '90px',
    left:         '50%',
    transform:    'translateX(-50%)',
    zIndex:       '99999',
    background:   colors[type] || colors.info,
    color:        '#fff',
    padding:      '12px 24px',
    borderRadius: '8px',
    fontSize:     '.9rem',
    maxWidth:     '90vw',
    textAlign:    'center',
    boxShadow:    '0 4px 20px rgba(0,0,0,.3)',
    animation:    'fadeInUp .3s ease',
  });

  const style = document.createElement('style');
  style.textContent = `
    @keyframes fadeInUp {
      from { opacity:0; transform:translateX(-50%) translateY(20px); }
      to   { opacity:1; transform:translateX(-50%) translateY(0); }
    }
  `;
  document.head.appendChild(style);
  document.body.appendChild(el);
  setTimeout(() => el.remove(), duration);
}
