/**
 * Unified WhatsApp Sharing Utility for Disaster Response System
 * Works seamlessly across desktop (WhatsApp Web) and mobile (WhatsApp App).
 */

(function(window) {
  'use strict';

  function sanitizePhone(phone) {
    if (!phone) return '';
    let clean = String(phone).replace(/\D/g, '');
    // Auto-prefix Indian country code if 10 digits starting with 6, 7, 8, 9
    if (clean.length === 10 && /^[6-9]/.test(clean)) {
      clean = '91' + clean;
    }
    return clean;
  }

  function getWhatsAppUrl(text, phone) {
    const encoded = encodeURIComponent((text || '').trim());
    const cleanPhone = sanitizePhone(phone);
    if (cleanPhone) {
      return `https://api.whatsapp.com/send?phone=${cleanPhone}&text=${encoded}`;
    }
    return `https://api.whatsapp.com/send?text=${encoded}`;
  }

  function shareToWhatsApp(options) {
    let text = '';
    let phone = '';

    if (typeof options === 'string') {
      text = options;
    } else if (options && typeof options === 'object') {
      text = options.text || '';
      phone = options.phone || '';
    }

    if (!text && !phone) {
      console.warn('shareToWhatsApp called without text or phone.');
      return;
    }

    const url = getWhatsAppUrl(text, phone);

    // Try opening in new tab
    const win = window.open(url, '_blank', 'noopener,noreferrer');
    if (!win || win.closed || typeof win.closed === 'undefined') {
      // If popup blocker intercepted, redirect current tab or inform user
      window.location.href = url;
    }
  }

  // Export functions to global scope
  window.shareToWhatsApp = shareToWhatsApp;
  window.getWhatsAppUrl = getWhatsAppUrl;
  window.sanitizePhone = sanitizePhone;

})(window);
