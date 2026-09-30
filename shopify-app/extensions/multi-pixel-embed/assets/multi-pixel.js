// Multi-Pixel storefront embed: sends PageView, ViewContent and Search to the Market Pixel of
// the Market this page was rendered for. Checkout events and AddToCart come from the app's
// Web Pixel (extensions/multi-pixel-checkout), which reads the market cookie set here.
(function () {
  var MARKET_COOKIE = '_mpx_market';

  var configEl = document.getElementById('multi-pixel-config');
  if (!configEl) return;
  var config;
  try {
    config = JSON.parse(configEl.textContent);
  } catch (e) {
    console.warn('[multi-pixel] bad config', e);
    return;
  }

  document.cookie =
    MARKET_COOKIE + '=' + encodeURIComponent(config.marketId || '') + '; path=/; max-age=2592000; SameSite=Lax';

  if (!config.pixelId) {
    console.info('[multi-pixel] no pixel mapped for market', config.marketId, config.marketHandle);
    return;
  }

  var pixelId = String(config.pixelId);

  function eventId() {
    return 'mpx-' + Date.now() + '-' + Math.random().toString(36).slice(2, 10);
  }

  // trackSingle, not track: another app (e.g. the Official Meta App) may have initialised its
  // own pixel on this page, and `track` would send to every initialised pixel.
  function track(name, data) {
    window.fbq('trackSingle', pixelId, name, data || {}, { eventID: eventId() });
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
        content_ids: [String(config.product.id)],
        content_type: 'product_group',
        content_name: config.product.name,
        value: config.product.price,
        currency: config.currency,
      });
    }

    if (config.template === 'search' && config.searchTerms) {
      track('Search', { search_string: config.searchTerms });
    }

    console.info('[multi-pixel] market', config.marketId, config.marketHandle, '-> pixel', pixelId);
  }

  // Consent: only fire once the shopper allows marketing (Shopify Customer Privacy API).
  function whenMarketingAllowed(callback) {
    var fired = false;
    function fire() {
      if (!fired) {
        fired = true;
        callback();
      }
    }

    document.addEventListener('visitorConsentCollected', function (event) {
      if (event.detail && event.detail.marketingAllowed) fire();
    });

    function check() {
      var privacy = window.Shopify && window.Shopify.customerPrivacy;
      if (privacy && privacy.marketingAllowed()) fire();
    }

    if (window.Shopify && window.Shopify.customerPrivacy) {
      check();
    } else if (window.Shopify && typeof window.Shopify.loadFeatures === 'function') {
      window.Shopify.loadFeatures([{ name: 'consent-tracking-api', version: '0.1' }], function (error) {
        if (error) {
          console.warn('[multi-pixel] consent API unavailable', error);
          return;
        }
        check();
      });
    } else {
      console.warn('[multi-pixel] Shopify consent API not found; not sending events');
    }
  }

  whenMarketingAllowed(sendPageEvents);
})();
