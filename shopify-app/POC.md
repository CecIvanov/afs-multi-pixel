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

## Install it on gpay3y-2v

`gpay3y-2v` is a real store, not a development store, so `shopify app dev` can't target it. The backend runs on the VPS, `shopify app deploy` releases the config and extensions, and the app is installed through a custom distribution link.

- App: **AFS Multi Pixel** (already linked in `shopify.app.toml`; don't re-run `shopify app config link`, because it overwrites the file with the app's remote settings).
- URL: `https://multi-pixel-test-app.adfeedstudio.com`
- Admin API version: `2026-10`


### 1. VPS (backend)

The VPS's existing Caddy terminates HTTPS and proxies to the container, which listens only on `127.0.0.1:33533` on the host (change it with `APP_PORT`; inside the container the app still uses 3000).

```sh
# on the VPS, in a copy of shopify-app/
cp .env.docker.example .env.docker   # then set SHOPIFY_API_SECRET in .env.docker (not in git)
docker compose up -d --build
```

Add to the Caddyfile, then reload Caddy:

```caddy
multi-pixel-test-app.adfeedstudio.com {
	reverse_proxy 127.0.0.1:33533
}
```

If Caddy itself runs in Docker, `127.0.0.1` is the Caddy container, not the host. In that case, put both on a shared Docker network and use `reverse_proxy <app-container-name>:3000`.

SQLite lives in the `data` volume (`/data/multi-pixel.sqlite`). Migrations run on start.

### 2. Release config and extensions (from your machine)

```sh
cd shopify-app
npm install
shopify app deploy        # releases URLs, scopes, webhooks and both extensions
```

### 3. Install and configure

1. Dev Dashboard → AFS Multi Pixel → **Distribution** → **Custom distribution** → enter `gpay3y-2v.myshopify.com` → open the install link as the store owner and approve.
2. In the store admin, open the app. Enter a Meta pixel ID for BG and for GR, then click **Save**.
3. **Online Store → Themes → Customize → App embeds**: switch on **Multi-Pixel**, then save.
4. Test in an incognito window on `test-subdomain1.adfeedstudio.com` (BG) and `test-subdomain2.adfeedstudio.com` (GR). Accept the cookie banner. The console shows `[multi-pixel] market <id> <handle> -> pixel <id>`. In Meta Events Manager → Test Events, each pixel should get only its own Market's events, including Purchase after a test order.

Updating: `docker compose up -d --build` on the VPS for backend changes; `shopify app deploy` for extension or config changes.
