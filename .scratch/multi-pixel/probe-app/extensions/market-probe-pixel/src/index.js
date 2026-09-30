import {register} from '@shopify/web-pixels-extension';

// Throwaway probe for the ticket "Set up a dev store with BG and RO Markets and capture
// real Web Pixel payloads". Logs raw payloads and tries sending to Meta's /tr endpoint.
// Not production code.

const META_EVENTS = {
  page_viewed: 'PageView',
  product_viewed: 'ViewContent',
  search_submitted: 'Search',
  product_added_to_cart: 'AddToCart',
  checkout_started: 'InitiateCheckout',
  payment_info_submitted: 'AddPaymentInfo',
  checkout_completed: 'Purchase',
};

const MARKET_COOKIE = '_mp_market';

const numericId = (id) => (id == null ? null : String(id).split('/').pop());

const parseMapping = (raw) =>
  Object.fromEntries(
    (raw || '')
      .split(',')
      .map((pair) => pair.split(':').map((s) => s.trim()))
      .filter(([marketId, pixelId]) => marketId && pixelId),
  );

register(({analytics, browser, init, settings}) => {
  const log = (label, data) =>
    console.log(`[market-probe] ${label}`, JSON.stringify(data, null, 2));

  const mapping = parseMapping(settings.mapping);
  log('init', {settings, mapping, init});

  const fbp = async () => {
    const existing = await browser.cookie.get('_fbp');
    if (existing) return existing;
    const created = `fb.1.${Date.now()}.${Math.floor(Math.random() * 1e10)}`;
    await browser.cookie.set('_fbp', created);
    return created;
  };

  const productIds = (event) => {
    const d = event.data || {};
    if (d.productVariant) return [d.productVariant.id];
    if (d.cartLine) return [d.cartLine.merchandise?.id];
    if (d.checkout) return (d.checkout.lineItems || []).map((l) => l.variant?.id);
    return [];
  };

  const valueAndCurrency = (event) => {
    const d = event.data || {};
    const money =
      d.checkout?.totalPrice || d.cartLine?.cost?.totalAmount || d.productVariant?.price;
    return money ? {value: money.amount, currency: money.currencyCode} : {};
  };

  const sendToMeta = async (event, marketId) => {
    const ev = META_EVENTS[event.name];
    const pixelId = mapping[marketId];
    if (!ev || !pixelId) {
      log('skip meta', {event: event.name, marketId, pixelId: pixelId || null});
      return;
    }
    const {value, currency} = valueAndCurrency(event);
    const params = new URLSearchParams({
      id: pixelId,
      ev,
      eid: event.id,
      dl: event.context?.document?.location?.href || '',
      rl: event.context?.document?.referrer || '',
      ts: String(Date.now()),
      fbp: await fbp(),
    });
    const ids = productIds(event).filter(Boolean);
    if (ids.length) {
      params.set('cd[content_ids]', JSON.stringify(ids));
      params.set('cd[content_type]', 'product');
    }
    if (value != null) params.set('cd[value]', String(value));
    if (currency) params.set('cd[currency]', currency);
    if (event.name === 'search_submitted') {
      params.set('cd[search_string]', event.data?.searchResult?.query || '');
    }
    const url = `https://www.facebook.com/tr/?${params}`;
    try {
      const res = await fetch(url, {method: 'GET', keepalive: true});
      log('meta sent', {event: event.name, ev, pixelId, marketId, status: res.status, url});
    } catch (error) {
      log('meta failed', {event: event.name, ev, pixelId, url, error: String(error)});
    }
  };

  let lastEmbedMarket = null;
  analytics.subscribe('market_probe:market', (event) => {
    lastEmbedMarket = event.customData;
    log('embed custom event', {receivedAt: Date.now(), event});
  });

  analytics.subscribe('all_standard_events', async (event) => {
    const cookieMarket = await browser.cookie.get(MARKET_COOKIE);
    const checkoutMarket = event.data?.checkout?.localization?.market;
    const marketId = numericId(checkoutMarket?.id) || numericId(cookieMarket);
    log(`event ${event.name}`, {
      receivedAt: Date.now(),
      market: {
        checkoutRaw: checkoutMarket || null,
        cookieRaw: cookieMarket || null,
        embedCustomEvent: lastEmbedMarket,
        resolved: marketId,
      },
      event,
    });
    await sendToMeta(event, marketId);
  });
});
