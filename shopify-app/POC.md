# Multi-Pixel POC

A Shopify app that sends Meta pixel events to a separate pixel per Shopify Market.

## What's in it

| Part | Where | Does |
|---|---|---|
| Backend + admin UI | `app/` (React Router, Prisma, SQLite) | OAuth install, stores the shop token (`Session`). Admin page: per Market a Meta pixel ID, a Conversions API token and an optional Test Events code (`MarketPixel`). Event log page. |
| Pixel Mapping publisher | `app/models/market-pixels.server.ts` | On save, mirrors `{ pixels, publicKey, endpoint }` to an app-owned metafield (theme embed) and to the Web Pixel's settings (checkout), and refreshes the storefront hosts allowed to call the relay. CAPI tokens never leave the server. |
| Theme app embed | `extensions/multi-pixel-embed` | Works out the Market in Liquid, sends **PageView, ViewContent (product, cart, collection), Search** with `fbq trackSingle`, and relays each event encrypted to the backend. Writes the market id to the `_mpx_market` cookie. |
| Web Pixel | `extensions/multi-pixel-checkout` | Sends **AddToCart** (Market from the cookie) and **InitiateCheckout, AddPaymentInfo, Purchase** (Market from the checkout) to Meta's `/tr`, and relays each one encrypted. Purchase uses event ID `purchase-<order id>`. |
| Relay + CAPI | `app/routes/api.events.tsx`, `app/models/relay*.server.ts`, `capi.server.ts` | Decrypts (RSA-OAEP + AES-GCM; key pair generated once and kept in SQLite), checks Origin, shop and that market → pixel is in the mapping, then sends the same event (same event ID, IP and user agent from the request, `_fbp`/`_fbc`) to `graph.facebook.com/v26.0/<pixel>/events` with that pixel's token. |
| Purchase join | `app/routes/webhooks.orders.create.tsx` | The relayed browser Purchase (exists only with marketing consent; carries the Market and Meta cookies) and the `orders/create` webhook (hashed email, phone, name, address) are joined on the order id; the server Purchase is sent once both are in. An order without a browser Purchase is never sent. |

Events go out only after the shopper allows marketing (Shopify Customer Privacy API). A Market with no pixel sends nothing; a Market without a CAPI token sends browser events only. `content_ids` are Shopify **product** ids with `content_type: product_group`, like the Official Meta App, which match AdFeed catalogs' `item_group_id`.

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

On the VPS, `.env.docker` must have `SCOPES=read_markets,write_pixels,read_customer_events,read_orders`.

### 2. Release config and extensions (from your machine)

Before the first deploy with `orders/create`: Dev Dashboard → AFS Multi Pixel → **API access → Protected customer data** → request access to protected customer data and the **name, email, phone and address** fields (reason: Meta Conversions API matching). For a custom-distribution app this is self-serve, without review. Without it, deploy refuses the `orders/create` subscription.

```sh
cd shopify-app
npm install
shopify app deploy        # releases URLs, scopes, webhooks and both extensions
```

### 3. Install and configure

0. If the app is already installed: after deploying, open the app in the store admin and **approve the new `read_orders` scope**.
1. Dev Dashboard → AFS Multi Pixel → **Distribution** → **Custom distribution** → enter `gpay3y-2v.myshopify.com` → open the install link as the store owner and approve.
2. In the store admin, open the app. For BG and GR enter the Meta pixel ID, the **Conversions API token** (Events Manager → the pixel's dataset → Settings → Conversions API → Generate access token) and, while testing, the **Test event code** (Events Manager → Test events). Click **Save**. Save again after every deploy that changes the relay, so the storefront gets the current key and endpoint.
3. **Online Store → Themes → Customize → App embeds**: switch on **Multi-Pixel**, then save.
4. Test in an incognito window on `test-subdomain1.adfeedstudio.com` (GR) and `test-subdomain2.adfeedstudio.com` (BG). Accept the cookie banner. The console shows `[multi-pixel] market <id> <handle> -> pixel <id>`. In Meta Events Manager → Test Events, each pixel should get only its own Market's events, including Purchase after a test order.

Checking the server side: the app's **Event log** page lists every event the backend received, with its Market, pixel, event ID and Meta's answer (`sent`, `error` with Meta's message, `rejected` with the reason, or `waiting` for the other half of a Purchase). With a Test event code set, server events show in Events Manager → Test events next to the browser events; a pair with the same event ID shows as deduplicated.

Updating: `docker compose up -d --build` on the VPS for backend changes; `shopify app deploy` for extension or config changes.
