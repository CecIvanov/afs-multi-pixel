# Research: which server-side bot signals are reliable enough to drop events?

Ticket: #18 (part of map #16, Bot Protection). Researched 2026-10-02.

Question: using only what the backend sees on a **Relay** (IP, user agent, Origin, rate, `fbp`/`fbc`, event sequence), which signals identify bots with a low false-positive rate? For each: false-positive risk, maintenance burden, licensing or cost.

## Short answer

Only one family of server-side signals is safe to **drop** on in v1: **a bot that names itself in the user agent.** Use the `isbot` package (already a dependency), plus a short rule of our own for a missing or empty user agent. Every other signal is either easy to forge or catches real shoppers often enough that it should only be **counted** (shadow), or used together with a self-declared bot, until UAT shows real numbers:

| Signal | Use in v1 | False-positive risk | Maintenance | Licence / cost |
|---|---|---|---|---|
| `isbot` user-agent match | **Drop** | Very low (real in-app browsers pass, see test below) | `npm`/`pip` bump; releases about monthly | Unlicense (public domain), free |
| Empty or missing user agent | **Drop** | Very low: every browser sends one | None | Free |
| Published crawler IP ranges (Google, Bing, OpenAI), only to *confirm* a UA claim | Optional confirm, not needed to drop | None when used to confirm | Daily JSON fetch | Free, first-party lists |
| Data-centre / cloud IP or ASN | **Shadow only** | **Medium to high**: iCloud Private Relay, VPNs, corporate proxies | Daily list refresh | Free (IPinfo Lite CC BY-SA 4.0, cloud vendor JSONs, MIT ASN list) or paid |
| Rate / bursts per IP | Keep the existing **limit**; burst rule shadow only | Medium: CGNAT, offices, Private Relay share IPs | Tuning | Free (Redis already there) |
| `fbp` / `fbc` shape and age | **Shadow only** | Medium: first visits, cookie blocking, ad blockers | Low | Free |
| Impossible funnel / event sequence | **Shadow only** | Medium to high: consent changes, ad blockers, cached pages, multiple tabs | Medium | Free |
| Origin check | Already a refusal (not a Bot Event) | Low for theme events; Web Pixel sends no Origin | None | Free |

The important context: **a Relay only exists if the shopper's browser ran our JavaScript and gave marketing consent** (`multi-pixel.js` line 7, Web Pixel `index.ts` line 21). Crawlers that only fetch HTML (most of them, including Meta's link-preview crawler) never send a Relay at all. The bots that do reach the Relay are **headless browsers** (monitoring, performance testing, scrapers, AI agents) and anyone **posting directly** to `/api/events`. That is why the user agent is the main honest signal and why a forged-from-scratch flood is a rate-limit problem, not a classification problem.

## What the backend sees today

From the code on `production` (c6e2c07):

- `shopify/app/relay-intake.shared.mjs`: the public `POST /api/events` forwards `origin`, `ip` (last `X-Forwarded-For` hop, set by our Caddy) and `user_agent` with the encrypted body.
- `backend/app/services/relay_service.py`: `RelayContext(origin, ip, user_agent)`; payload carries `event`, `eventId`, `eventTime`, `url`, `fbp`, `fbc`, `marketId`, `pixelId`, `customData`. Rate limit: 120 Relays per IP per minute, 6000 per shop per minute, fixed one-minute windows in Redis, fail-open (`config.py` lines 90-91). `_refusal` is the hook named on the map.
- The envelope is encrypted with a public key that is printed into every storefront page (`blocks/*.liquid`, `config.endpoint` and key). **Encryption hides content in transit but does not prove the sender is our script**; anyone can build valid envelopes. So nothing in the payload is trustworthy evidence against a determined forger.
- The checkout Web Pixel **creates `_fbp` itself if it is missing** (`multi-pixel-checkout/src/index.ts` lines 79-87), so `fbp` presence says nothing about checkout events.
- `strip_personal_data` (`server_event_sender.py` line 80) blanks `user_data` (IP, UA, fbp, fbc) once an event is final. So **the bot decision must be made at receive time**, and any evidence kept for the "why was this blocked?" sample has to be copied before stripping (privacy question already on the map).

## 1. Crawler user-agent lists (`isbot`)

**What it is.** `isbot` (npm, by omrilotan) matches a user agent against one combined regular expression built from several maintained lists: Kikobeats/top-crawler-agents, monperrus/crawler-user-agents, stephenafamo/isbot, Matomo, myip.ms, user-agents.net, ua-parser-js, plus manual bot and not-bot lists ([README](https://github.com/omrilotan/isbot)). Exports `isbot`, `isbotMatch`, `isbotMatches`, `createIsbot`, `createIsbotFromList`, `list`.

**What it does not do**, in its own words: it "does not try to recognise malicious bots or programs disguising themselves as real users"; it targets bots that "voluntarily identify themselves" ([README](https://github.com/omrilotan/isbot)).

**Test against the user agents that matter to us** (isbot 5.2.2, run 2026-10-02):

| User agent | Result | Matched on |
|---|---|---|
| Chrome desktop, iPhone Safari, Android WebView | human | |
| Facebook in-app browser (`FBAN/FBIOS`) | human | |
| Instagram in-app browser | human | |
| Google app (`GSA/`), TikTok in-app | human | |
| `facebookexternalhit/1.1` | **bot** | `facebook` |
| `meta-externalagent/1.1`, `meta-externalads/1.1`, `facebookcatalog/1.0` | **bot** | |
| Googlebot smartphone, Google-InspectionTool, AdsBot-Google, Bingbot | **bot** | |
| `HeadlessChrome/128` | **bot** | `Headless` |
| PageSpeed / Lighthouse (`Chrome-Lighthouse`) | **bot** | `Chrome-Lighthouse` |
| GPTBot, ChatGPT-User, PerplexityBot | **bot** | |
| Pingdom, `Shopify-Captain-Hook`, `python-requests`, `curl` | **bot** | |
| **empty string** | **human** | |

So the in-app browsers that carry most Meta ad traffic pass, which is the false positive that would hurt most. An empty user agent is **not** flagged by `isbot`, so we need our own rule (Cloudflare's heuristics engine treats a missing or empty UA as a score of 1, "automated", [Cloudflare bot score](https://developers.cloudflare.com/bots/concepts/bot-score/)).

**Limit to know.** Since Chrome 132 the old headless mode is a separate `chrome-headless-shell` binary ([Chrome docs](https://developer.chrome.com/docs/chromium/headless)); a headless browser whose operator sets a normal UA is invisible to this rule. That is the gap #17 (client-side signals) must cover.

- **False-positive risk:** very low on the cases above. The one realistic risk is a merchant's **own** monitoring or performance tools (Pingdom, Lighthouse) being blocked, which is correct by definition (they are not shoppers) but is the case for the "allow-list" item on the map.
- **Maintenance:** releases are frequent (5.1.36 to 5.2.2 between March and August 2026, about monthly; npm registry). The Python backend would need the same list: either decide in the Remix intake (which already has `isbot`) and forward the verdict, or port `isbot`'s `list` (it is exported) to Python on each bump. Deciding in the intake avoids two lists drifting.
- **Licence / cost:** Unlicense (public domain), free.

## 2. Meta's own fetchers (`facebookexternalhit` and others)

Meta documents five crawler user agents: `FacebookExternalHit` (link previews when a URL is shared), `Meta-WebIndexer`, `Meta-ExternalAds` ("improving advertising and other business-related products"), `Meta-ExternalAgent` (AI training and indexing) and `Meta-ExternalFetcher` (user-requested fetches for AI agents) ([Meta web crawlers](https://developers.facebook.com/docs/sharing/webmasters/web-crawlers/)). `FacebookExternalHit` "might bypass robots.txt when performing security or integrity checks". The page points to allow-listing by "user agent strings or the IP addresses (more secure)" but does not publish an IP list on the current page.

All five are self-declared and all are caught by `isbot` (table above). Meta does not document whether these crawlers run JavaScript; in practice it only matters if they do, because without JS there is no Relay. If they do, dropping their events is right: they are not shoppers.

- **False-positive risk:** none for the crawler UAs. Do **not** confuse with the in-app browser (`FBAN`/`FBAV`, `Instagram`), which is real shoppers and passes.
- **Maintenance / cost:** covered by `isbot`.

## 3. Shopify-specific traffic

- **Theme editor and preview.** Liquid's `request.design_mode` "returns true if the request is being made from within the theme editor", and Shopify's docs say it can be used to "prevent session data from being tracked by tracking scripts in the theme editor"; `request.visual_preview_mode` covers the section preview ([Liquid request object](https://shopify.dev/docs/api/liquid/objects/request)). This is visible only at render time, so the server sees it only if the embed puts it into the Relay. **Recommendation:** have the embed skip the editor itself (client-side, #17), not a server rule. Merchants clicking around their own theme editor is the most common "fake PageView" a Shopify merchant will notice.
- **Shopify's performance testing.** Shopify "tests the app's effect on store performance by measuring the Lighthouse score before and after the app is installed" ([Storefront performance](https://shopify.dev/docs/apps/build/performance/storefront)), and the store speed report is based on Lighthouse runs of the home, top product and top collection pages ([speed report](https://help.shopify.com/en/manual/online-store/store-speed/speed-report)). Lighthouse sends `Chrome-Lighthouse` in its UA, which `isbot` catches. Whether these runs reach our Relay depends on consent: where consent is required and not given, nothing is sent.
- **Shopify's edge bot protection.** "All requests that come to your online store on Shopify must first pass through Cloudflare", which uses WAF and DDoS protection "to shield your store from the majority of automated traffic and bots" ([Dealing with bots](https://help.shopify.com/en/manual/intro-to-shopify/bots/dealing-with-bots)). That protects page loads, **not our Relay endpoint**, which is on our VPS behind Caddy. Checkout additionally has hCaptcha by default and Plus-only checkout bot protection ([same page](https://help.shopify.com/en/manual/intro-to-shopify/bots/dealing-with-bots), [checkout bot protection](https://help.shopify.com/en/manual/checkout-settings/bot-protection)), which fits the map's rule that a Purchase tied to a real order is never a Bot Event.
- **Shopify's own server-side agents** (for example `Shopify-Captain-Hook`, the webhook sender) never run storefront JavaScript, so they cannot produce a Relay; `isbot` would flag them anyway.

## 4. Data-centre / ASN IP lists

**Sources and licences:**

| Source | What | Licence / cost | Refresh |
|---|---|---|---|
| IPinfo Lite | IP to ASN, AS name, AS domain, country | CC BY-SA 4.0, free incl. commercial, attribution link required ([IPinfo Lite](https://ipinfo.io/lite)) | Daily |
| MaxMind GeoLite2 ASN | IP to ASN | GeoLite EULA: account and licence key, "internal business purposes", attribution line, must destroy old versions within 30 days of a new release, no disclosure to third parties without consent ([EULA](https://www.maxmind.com/en/geolite2/eula)) | Not stated on the page; old copies must go within 30 days |
| Cloud vendor ranges | AWS `ip-ranges.json`, Google Cloud `cloud.json`, Oracle `public_ip_ranges.json`, DigitalOcean `geo/google.csv` | Free, first-party | AWS regenerates several times a day (10,547 prefixes on 2026-10-02) |
| `brianhama/bad-asn-list` | ASNs of cloud, hosting, colo | MIT, community, last push 2026-04 | Irregular |
| `X4BNet/lists_vpn`, `jhassine/server-ip-addresses` | Data-centre and VPN CIDRs | **No licence file** on GitHub, so not safe to ship | Daily |
| Paid (IPinfo privacy/hosting flags, MaxMind Anonymous IP) | "is hosting", VPN, proxy, relay flags | Paid subscription | Daily |

The free ASN databases give the **network owner**, not a "this is a data centre" flag; we would still need our own list of hosting ASNs.

**The false-positive problem.** Apple's iCloud Private Relay sends Safari traffic of iCloud+ subscribers through egress IPs that geo-IP providers annotate with fields like `is_hosting` or `privacy_proxy`, and Apple says to "treat relay IP addresses similar to carrier-grade NAT or enterprise IPs" and "avoid traditional IP-based blocking that would impact legitimate users" ([Apple: Prepare your network for iCloud Private Relay](https://developer.apple.com/support/prepare-your-network-for-icloud-private-relay/)). The published egress list (`mask-api.icloud.com/egress-ip-ranges.csv`) had about 285,000 ranges on 2026-10-02. Private Relay runs on large CDN networks, so a "cloud/CDN ASN = bot" rule would drop real iPhone shoppers, the most valuable Meta audience. Corporate proxies and consumer VPNs add more.

- **False-positive risk:** medium to high on its own. Acceptable only as a **shadow count**, or combined with a self-declared bot UA, or after subtracting the Private Relay list.
- **Maintenance:** a daily job to fetch and index lists; ASN lists need manual curation.
- **Licence:** IPinfo Lite is the cleanest free option (CC BY-SA, commercial use allowed, just a link). GeoLite2 adds an account, EULA and the 30-day deletion duty.

**Verifying claimed crawlers** (the opposite use, safe): Google publishes `googlebot.json`, `special-crawlers.json` and `user-triggered-fetchers.json` and also supports reverse DNS to `googlebot.com` / `google.com` / `googleusercontent.com` ([Verifying Googlebot](https://developers.google.com/search/docs/crawling-indexing/verifying-googlebot)); Bing (`bing.com/toolbox/bingbot.json`) and OpenAI (`openai.com/gptbot.json`) publish JSON lists too. We do not need this to **drop** (a UA claiming to be a bot is dropped either way), only if we ever wanted to treat verified crawlers differently from impostors in the sample list.

## 5. Behavioural patterns

None of these has a published, first-party false-positive figure; they are heuristics to measure in shadow mode on the UAT App.

- **Rate and bursts per IP.** Already enforced as a limit (120 per IP per minute). Shared IPs (mobile CGNAT, offices, Private Relay, which Apple compares to CGNAT) make a tight per-IP rule risky. Keep the limit as flood protection (a "limited" answer, not a Bot Event), and only *count* bursts such as "N distinct `fbp`s from one IP in a minute" until real data exists.
- **`fbp` / `fbc` shape and age.** Meta's format is `fb.<subdomainIndex>.<creationTime>.<random>` for `_fbp` and `fb.<subdomainIndex>.<creationTime>.<fbclid>` for `_fbc`; the pixel creates `_fbp` when it loads ([fbp and fbc](https://developers.facebook.com/docs/marketing-api/conversions-api/parameters/fbp-and-fbc/)). Signals: malformed values (strong, cheap); `fbp` creation time in the future (strong); a **new `fbp` on every event from the same IP and UA** (a client that keeps no cookies, typical of fresh headless profiles). A **missing** `fbp` is weak: ad blockers stop `fbevents.js` while our Relay may still go out, and the theme embed sends without `fbp` after its wait (`waitForFbp` in `multi-pixel.js`). The checkout pixel mints its own `fbp`, so none of this applies to checkout events.
- **Impossible funnels.** For example AddToCart with no prior PageView/ViewContent for that `fbp`, or InitiateCheckout seconds after the first PageView. Real causes of the same pattern: consent granted mid-session, ad blockers, a cached or restored page, several tabs, the Web Pixel and theme embed racing. High false-positive risk and needs a lookup across `server_events` at receive time; **shadow only**.
- **Malformed payload** (bad `eventId`, unknown Market) is already a refusal, which is the right home: these are broken or forged requests, not bot shoppers.

## Recommendation for the spec (#21 decides where the decision lives)

1. **Drop rule v1 (server side):** `isbot(userAgent)` true, or user agent missing/empty. Reason codes: `bot_user_agent` (with the `isbotMatch` substring as evidence) and `no_user_agent`. Never for a Purchase tied to a real order.
2. **Decide in the Remix intake** where `isbot` already lives, and forward a verdict and matched substring to the backend; or port `isbot`'s exported `list` to Python and refresh it on each release. One list, one place.
3. **Shadow counters, not drops:** data-centre ASN (IPinfo Lite, minus the Private Relay list), per-IP bursts of distinct `fbp`s, malformed/future `fbp`, cookie-less repeat clients, impossible funnels. Promote any of them to a drop rule only after UAT numbers show a low false-positive rate.
4. **Theme editor:** handled client-side with `request.design_mode` (#17), not by a server rule.
5. **Make the decision at receive time** and copy the minimal evidence (reason, matched UA substring) before `strip_personal_data` runs, which feeds the "Bot evidence and privacy" item on the map.

## Not verified

- Whether Meta's and Shopify's fetchers execute JavaScript (and so whether they ever reach the Relay at all). Shadow mode on UAT will show it.
- The exact URLs or headers of theme editor and theme preview page loads as seen by our Relay (`url` field); worth logging on the UAT store before writing any URL rule.
