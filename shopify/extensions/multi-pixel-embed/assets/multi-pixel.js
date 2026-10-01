// AFS Multi Pixel theme app embed (spec §3.1): sends PageView, ViewContent (product,
// cart and collection pages) and Search to the Market Pixel of the Market this page
// was rendered for, and relays each event, encrypted, to the app, which sends the
// same event (same event ID) to the Conversions API. AddToCart and the checkout
// events come from the app's Web Pixel (extensions/multi-pixel-checkout), which reads
// the Market cookie written here. Event shapes follow the Official Meta App.
// Nothing loads or sends without marketing and sale-of-data consent.
(function () {
  var MARKET_COOKIE = '_mpx_market';

  var configEl = document.getElementById('afs-multi-pixel-config');
  if (!configEl) return;
  var config;
  try {
    config = JSON.parse(configEl.textContent);
  } catch (e) {
    console.warn('[afs-multi-pixel] bad config', e);
    return;
  }

  document.cookie =
    MARKET_COOKIE + '=' + encodeURIComponent(config.marketId || '') + '; path=/; max-age=2592000; SameSite=Lax';

  // A Market with no pixel sends nothing (spec §2).
  if (!config.pixelId) return;

  var pixelId = String(config.pixelId);
  var ids = function (list) {
    return (list || []).map(String);
  };

  function eventId() {
    return 'mpx-' + Date.now() + '-' + Math.random().toString(36).slice(2, 10);
  }

  function cookie(name) {
    var match = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'));
    return match ? decodeURIComponent(match[1]) : undefined;
  }

  // --- encrypted relay to the backend (hybrid RSA-OAEP + AES-GCM) ---------------------------------

  function toB64(buffer) {
    var bytes = new Uint8Array(buffer);
    var binary = '';
    for (var i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
    return btoa(binary);
  }

  function fromB64(value) {
    var binary = atob(value);
    var bytes = new Uint8Array(binary.length);
    for (var i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    return bytes;
  }

  var rsaKey = null;
  function publicKey() {
    if (!rsaKey) {
      rsaKey = crypto.subtle.importKey('spki', fromB64(config.publicKey), { name: 'RSA-OAEP', hash: 'SHA-256' }, false, [
        'encrypt',
      ]);
    }
    return rsaKey;
  }

  function encrypt(payload) {
    var iv = crypto.getRandomValues(new Uint8Array(12));
    return crypto.subtle.generateKey({ name: 'AES-GCM', length: 256 }, true, ['encrypt']).then(function (aesKey) {
      var plain = new TextEncoder().encode(JSON.stringify(payload));
      return Promise.all([
        crypto.subtle.encrypt({ name: 'AES-GCM', iv: iv }, aesKey, plain),
        crypto.subtle.exportKey('raw', aesKey).then(function (raw) {
          return publicKey().then(function (rsa) {
            return crypto.subtle.encrypt({ name: 'RSA-OAEP' }, rsa, raw);
          });
        }),
      ]).then(function (parts) {
        return JSON.stringify({ v: 1, k: toB64(parts[1]), iv: toB64(iv), d: toB64(parts[0]) });
      });
    });
  }

  // _fbp is written by fbevents.js once it has loaded; give it a moment on the first event.
  function waitForFbp(attempts) {
    return new Promise(function (resolve) {
      (function poll(left) {
        var fbp = cookie('_fbp');
        if (fbp || left <= 0) return resolve(fbp);
        setTimeout(function () {
          poll(left - 1);
        }, 200);
      })(attempts);
    });
  }

  function relay(name, id, data) {
    if (!config.endpoint || !config.publicKey || !window.crypto || !crypto.subtle) return;
    waitForFbp(10)
      .then(function (fbp) {
        return encrypt({
          shop: config.shop,
          event: name,
          eventId: id,
          eventTime: Date.now(),
          marketId: config.marketId,
          pixelId: pixelId,
          url: location.href,
          fbp: fbp,
          fbc: cookie('_fbc'),
          customData: data,
        });
      })
      .then(function (body) {
        return fetch(config.endpoint, {
          method: 'POST',
          mode: 'no-cors',
          keepalive: true,
          headers: { 'Content-Type': 'text/plain' },
          body: body,
        });
      })
      .catch(function (error) {
        console.warn('[afs-multi-pixel] relay failed', name, error);
      });
  }

  // trackSingle, not track: another app (e.g. the Official Meta App) may have initialised its
  // own pixel on this page, and `track` would send to every initialised pixel.
  function track(name, data) {
    var id = eventId();
    window.fbq('trackSingle', pixelId, name, data || {}, { eventID: id });
    relay(name, id, data || {});
  }

  function loadMetaPixel() {
    /* Meta pixel base code */
    !(function (f, b, e, v, n, t, s) {
      if (f.fbq) return;
      n = f.fbq = function () {
        n.callMethod ? n.callMethod.apply(n, arguments) : n.queue.push(arguments);
      };
      if (!f._fbq) f._fbq = n;
      n.push = n;
      n.loaded = !0;
      n.version = '2.0';
      n.queue = [];
      t = b.createElement(e);
      t.async = !0;
      t.src = v;
      s = b.getElementsByTagName(e)[0];
      s.parentNode.insertBefore(t, s);
    })(window, document, 'script', 'https://connect.facebook.net/en_US/fbevents.js');

    window.fbq('set', 'autoConfig', false, pixelId);
    window.fbq('init', pixelId);
  }

  function sendPageEvents() {
    loadMetaPixel();
    track('PageView');

    if (config.product) {
      track('ViewContent', {
        content_ids: ids([config.product.id]),
        content_type: 'product_group',
        content_name: config.product.name,
        content_category: config.product.type || undefined,
        value: config.product.price,
        currency: config.currency,
      });
    }

    if (config.cart && config.cart.productIds.length) {
      track('ViewContent', {
        content_ids: ids(config.cart.productIds),
        content_type: 'product_group',
        value: config.cart.value,
        currency: config.currency,
        num_items: config.cart.numItems,
      });
    }

    if (config.collection && config.collection.productIds.length) {
      track('ViewContent', {
        content_ids: ids(config.collection.productIds),
        content_type: 'product_group',
        content_category: config.collection.name,
      });
    }

    if (config.template === 'search' && config.searchTerms) {
      track('Search', { search_string: config.searchTerms });
    }

  }

  // Consent (spec §3.1): fbevents.js loads and events fire only once the shopper
  // allows marketing AND the sale of data (Shopify Customer Privacy API, read
  // from the store's own cookie banner).
  function whenConsented(callback) {
    var fired = false;
    function allowed(privacy) {
      return privacy && privacy.marketingAllowed() && privacy.saleOfDataAllowed();
    }
    function check() {
      if (!fired && allowed(window.Shopify && window.Shopify.customerPrivacy)) {
        fired = true;
        callback();
      }
    }

    document.addEventListener('visitorConsentCollected', check);

    if (window.Shopify && window.Shopify.customerPrivacy) {
      check();
    } else if (window.Shopify && typeof window.Shopify.loadFeatures === 'function') {
      window.Shopify.loadFeatures([{ name: 'consent-tracking-api', version: '0.1' }], function (error) {
        if (!error) check();
      });
    }
  }

  whenConsented(sendPageEvents);
})();
