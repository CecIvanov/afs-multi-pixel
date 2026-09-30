# Market probe (throwaway)

This app exists for the ticket [Set up a dev store with BG and RO Markets and capture real Web Pixel payloads](../issues/06-dev-store-with-markets.md). It is not the product. Delete it once the ticket is resolved.

- `extensions/market-probe-pixel`: a strict Web Pixel. For every Standard Funnel event it logs the raw payload, the Market it can see (from the checkout payload, the embed's cookie and the embed's custom event) and its arrival time. It then sends the event to Meta's `/tr` endpoint for the mapped Market Pixel.
- `extensions/market-probe-embed`: a theme app embed. It renders `{{ localization.market.id }}` from Liquid, writes it to a `_mp_market` cookie, publishes a `market_probe:market` custom event and logs itself.

Every log line starts with `[market-probe]` or `[market-probe-embed]` in the browser console.

## Checklist (needs your accounts)

### 1. Store

- [ ] In the Shopify Partner dashboard, create a **development store**. Note its URL.
- [ ] **Settings → Markets**: create a **Bulgaria** Market (country BG) and a **Romania** Market (country RO), both active. Make sure the storefront can reach each one: use a country selector in the theme, or subfolders `/bg`, `/ro`.
- [ ] Add 2–3 **products with variants and SKUs**.
- [ ] **Settings → Payments**: enable the **Bogus Gateway** (test card: `1`).
- [ ] **Settings → Customer privacy**: note whether a consent banner shows. The probe pixel needs **marketing consent**, so accept everything in the banner during tests.

### 2. Meta

- [ ] In Events Manager, create **two test pixels (datasets)**: `probe-BG` and `probe-RO`. Note their IDs.

### 3. Run the app

```sh
cd .scratch/multi-pixel/probe-app
npm install
shopify app config link   # create a new app called "market-probe"
shopify app dev           # choose the dev store and install the app
```

- [ ] In the dev store's **theme editor → App embeds**, switch on **Market probe** and save.
- [ ] In the `shopify app dev` terminal, press **g** to open **GraphiQL**. Run the query below and **save the output** to `../probe-logs/markets.json`:

```graphql
{ markets(first: 20) { nodes { id handle name } } }
```

- [ ] Using the numeric part of each market id (`gid://shopify/Market/<number>`), activate the pixel with the mapping:

```graphql
mutation {
  webPixelCreate(webPixel: { settings: "{\"mapping\":\"<BG_MARKET_NUM>:<BG_PIXEL_ID>,<RO_MARKET_NUM>:<RO_PIXEL_ID>\"}" }) {
    webPixel { id settings }
    userErrors { field message code }
  }
}
```

(If the pixel already exists, use `webPixelUpdate(id: "<webPixel id>", webPixel: {...})`.)

### 4. Scenarios

Before each scenario, open a **fresh incognito window** with DevTools → Console open and **Preserve log** switched on. Also open **Events Manager → Test Events** for both pixels. At the end of each scenario, right-click the console → **Save as…** into `../probe-logs/<scenario>.log`.

- [ ] **A-bg**: enter the store as the BG Market → open a product → search → add to cart → checkout → pay with Bogus → Thank you page.
- [ ] **B-ro**: the same, in the RO Market.
- [ ] **C-switch**: start in BG, view a product, switch to RO with the country selector, view a product, then check out and purchase.
- [ ] **D-address**: start in BG, go to checkout, enter a **Romanian shipping address**, then purchase. Did the checkout's Market change?
- [ ] **E-no-embed**: switch the app embed **off** and run a short BG browse (product view only). This shows what the pixel sees without it.

### 5. Report back

Tell me the following. I'll read the logs for everything else.

- whether each pixel's **Test Events** (or Overview, after about 20 minutes) showed the events, and in the right pixel;
- the **Event Match Quality** / warnings Events Manager shows, if any;
- anything odd, such as consent prompts or errors in the console.
