# Multi-Pixel POC

A Shopify app that sends Meta pixel events to a separate pixel per Shopify Market.

## What's in it

| Part | Where | Does |
|---|---|---|
| Backend + admin UI | `app/` (React Router, Prisma, SQLite) | OAuth install, stores the shop token (`Session` table), loads the store's Markets and saves a pixel ID per Market (`MarketPixel` table). |
| Pixel Mapping publisher | `app/models/market-pixels.server.ts` | On save, mirrors the mapping `{ marketId: pixelId }` to an app-owned metafield (read by the theme embed) and to the Web Pixel's settings (read in checkout). |
| Theme app embed | `extensions/multi-pixel-embed` | Works out the Market in Liquid (`localization.market.id`), looks up its pixel, loads Meta's pixel and sends **PageView, ViewContent, Search** with `trackSingle`. Writes the market id to the `_mpx_market` cookie. |
| Web Pixel | `extensions/multi-pixel-checkout` | Sends **AddToCart** (Market from the `_mpx_market` cookie) and **InitiateCheckout, AddPaymentInfo, Purchase** (Market from the checkout itself) to Meta's `/tr` endpoint. Theme code doesn't run in checkout, so Purchase has to come from here. |

Events go out only after the shopper allows marketing (Shopify Customer Privacy API). A Market with no pixel sends nothing. `content_ids` are Shopify **product** ids with `content_type: product_group`.

## Run it on the dev store (fastest)

The app must live in the **Dev Dashboard / Partner Dashboard**. An app created in the store admin under "Develop apps" can't have extensions.

```sh
cd shopify-app
npm install
shopify app config link   # connect to the POC app (or create one); fills client_id
shopify app dev           # choose gpay3y-2v; opens a tunnel, pushes scopes/URLs/extensions, installs
```

1. In the store admin, open the app. Each Market gets a field: enter a Meta pixel ID for BG and for GR, then click **Save**.
2. **Online Store → Themes → Customize → App embeds**: switch on **Multi-Pixel**, then save.
3. Test in an incognito window on `test-subdomain1.adfeedstudio.com` (BG) and `test-subdomain2.adfeedstudio.com` (GR). Accept the cookie banner. The console shows `[multi-pixel] market <id> <handle> -> pixel <id>`. In Meta Events Manager → Test Events, each pixel should get only its own Market's events, including Purchase after a test order.

## Run it in Docker

```sh
cp .env.docker.example .env.docker   # fill in API key/secret and the public URL
docker compose up -d --build
```

- Set `application_url` and `redirect_urls` in `shopify.app.toml` to the public URL, then run `shopify app deploy`. That pushes the config and both extensions; the container only serves the backend.
- SQLite lives in the `data` volume (`/data/multi-pixel.sqlite`). Migrations run on start.
