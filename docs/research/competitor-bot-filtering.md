# How competing tracking apps sell and implement bot filtering

Research for issue #20, part of map #16 (Bot Protection). Gathered 2026-10-02 from the vendors' own docs, marketing pages and Shopify App Store listings. Vocabulary follows `CONTEXT.md` (**Bot Event**, **Bot Protection**, **Browser Event**, **Server Event**, **Relay**).

## Summary

- **Only a few apps have it.** Littledata, Stape, Aimerce and Orichi (OC Meta Pixel, a direct multi-pixel competitor) sell bot or spam filtering. Elevar shipped a one-line "exclude bot traffic" change in 2023 but does not market or document it. Their own pages for TrackBee, Trackify X and Analyzify say nothing about bots.
- **Nearly all of it runs on the server.** Littledata, Stape, Aimerce and Elevar filter **Server Events** before they reach destinations. Orichi is the only one that does anything in the browser, and its documented check is a single rule: a Purchase with no `order_id` is dropped before `fbq` fires.
- **None of them says much about how detection works.** Littledata names attack patterns. Stape names "request parameters" plus bot databases and a 0–100 score. Aimerce and Orichi say nothing about signals. Nobody publishes a false-positive rate or a "% junk removed" figure.
- **Merchants see very little.** No vendor documents a per-event "why was this blocked" view. Littledata shows aggregate filter activity "during beta". Stape adds headers that the merchant uses in their own GTM triggers.
- **Defaults and plans vary.** Littledata and Stape are **off by default** and switched on by the merchant (Littledata per destination). Littledata includes it on every plan, Stape only on Pro and above, and Orichi only on paid plans (not the free Development plan).

## Per vendor

### Littledata

| | |
|---|---|
| What it detects | "Headless bots that hit your store and fire fake Cart or Checkout activity"; "Direct attacks against your destination endpoints, for example bots posting events straight to a public GA4 measurement ID"; "Consistent volume attacks with a steady cadence"; "Randomized or low-frequency, high-quantity attacks where timing alone wouldn't flag them". [help] |
| Explicitly not covered | Bots that simulate real browser sessions, auto-checkout bots that complete real purchases, and events other than Cart and Checkout. [help] |
| Where | Server side, at the "Shopify event level before they reach any destination". It is pitched as "Coverage where Shopify's protection stops", since "many bot mitigations work at the page level, but bots can inject fake events via API". [marketing] |
| Method | The two pages disagree. The help page says "deterministic checks rather than probabilistic scoring". The marketing page says "probabilistic filters to minimise the risk of blocked real conversion events", and adds that "in the next iteration you'll be able to tweak this probability in settings". [help] [marketing] |
| Destinations | GA4, Meta CAPI, Google Ads, and Klaviyo (where it stops profiles being created for bot checkouts). [help] |
| What the merchant sees | Filtered events are missing from destination reports. Aggregate filter activity is shown "during beta". No per-event view. [help] |
| Default / control | Off. Opt-in per destination under Settings > General. [help] |
| Plan | Every plan (Flex, Advanced/Scale, Plus). The plans page marks "Bot protection" true for flex, advanced and plus. [plans] [listing] |
| Wording | "bot filtering - built in"; "Shopify Markets and bot protection" (App Store). "Cleaner funnel data, more reliable attribution", and ad platforms "optimize on real users instead of headless traffic". [listing] [help] |

Sources: [help](https://help.littledata.io/sources/shopify/bot-protection), [marketing](https://www.littledata.io/bot-protection), [plans](https://www.littledata.io/plans), [listing](https://apps.shopify.com/littledata).

### Stape (server-GTM hosting, Bot Detection power-up)

| | |
|---|---|
| What it detects | It "analyzes the request parameters and compares them to private and public bot databases". [docs] |
| Output | It adds headers `X-Device-Bot` (true/false) and `X-Device-Bot-Score` (0–100). Below 50 means "highly likely to be a real human user", 50–75 means "suspicious", and above 75 means "confirmed bot traffic". [docs] |
| Where | Server side, in the Stape container. |
| Action | Either the merchant adds the header as a trigger condition ("Add this variable as an additional condition to your GA4 trigger, or any other trigger…"), or Stape "automatically blocks bot requests to `/collect` (GA4) and `/data` (Data Tag) paths if traffic is scoring above 75". [docs] |
| Guidance | Block above 75. For 50–75, "Do not block it… treat it as a watchlist rather than a verdict". Apply the bot exception to ad-platform tags, Meta CAPI included. On false positives: "Better to report on a small percentage of bot traffic than to block a percentage of real traffic." It treats a screen resolution of 0x0 as "close to a guarantee that no human is present". [blog] |
| What the merchant sees | Nothing documented beyond the headers and toggle. [docs] |
| Default / plan | Off ("Toggle the Bot Detection switch to enable it"). "Available on the Pro subscription plan and higher." [docs] |

Sources: [docs](https://stape.io/helpdesk/documentation/bot-detection-power-up), [product page](https://stape.io/solutions/bot-detection), [blog](https://stape.io/blog/practical-guide-to-bot-proofing-ad-bidding).

### Aimerce

- The App Store listing says "Identify more of your website traffic and built-in bot filtering". Pricing starts at $299/month. [listing](https://apps.shopify.com/aimerce)
- The control is an "Enable Bot Filtering" toggle on the Meta CAPI connection, under "Settings, under Meta Dataset (Pixel)". Its stated purpose is to keep the "Meta Ads algorithm from being trained on bot data signals". It also claims "Meta Ads currently does not have a filter in place to differentiate bot traffic from real prospects". [blog](https://www.aimerce.ai/blogs/Meta_Ads_Bot_Filtering)
- Signals, default state and what the merchant sees are not documented. Filtering is server side (CAPI connection).

### Orichi: OC Meta Pixel (multi-pixel, direct competitor)

- The listing says "block spam & fake purchase events, clean data trains the algorithm correctly". Its plan feature is "Spam & fake event blocking", included on Basic ($14.99/mo) and Advanced ($24.99/mo) but **not** on the free Development plan. [listing](https://apps.shopify.com/yuri-facebook-multi-pixels)
- It defines the threat as "purchase scripts", meaning a script that fires a Purchase on a competitor's pixel to poison its audience. The rule it documents runs in the browser and wraps `fbq`: `if (arguments[1] === "Purchase" && typeof arguments[2].order_id === "undefined") return;` [blog](https://orichi.info/how-to-block-fake-purchases-events-spam-events/)
- How the app itself decides is not documented beyond "leveraging … Conversion API" and deduplication.

### Elevar

- Changelog v3.6 (20 Jul 2023), under All Destinations Enhancements: "Exclude bot traffic from server-side tracking". No further detail. [changelog](https://docs.getelevar.com/changelog/v36-july-20th-2023)
- The GA4 bot-traffic doc only says to "reach out to the Elevar Support Team". [doc](https://docs.getelevar.com/docs/filtering-bot-traffic-in-google-analytics-4-reporting)
- The App Store listing does not mention bots. [listing](https://apps.shopify.com/gtm-datalayer-by-elevar) So it is not a selling point.

### TrackBee, Trackify X, Analyzify

The App Store listings and product pages for all three never mention bots, spam or fake events ([trackbee.ai/tracking](https://www.trackbee.ai/tracking), [apps.shopify.com/trackbee](https://apps.shopify.com/trackbee), [trackifyapp.com](https://www.trackifyapp.com/), [apps.shopify.com/trackify-1](https://apps.shopify.com/trackify-1), [apps.shopify.com/analyzify](https://apps.shopify.com/analyzify), [docs.analyzify.com/meta-server-side-guide](https://docs.analyzify.com/meta-server-side-guide)). Third-party "alternative" pages say they have no bot filtering, but those come from a rival vendor and are not used as evidence here.

### Other multi-pixel apps on the App Store

The other multi-pixel listings in our earlier competitor research (Avantify, Conversios, Facebook Multi Pixels, FBTrack, HypaPixel, Nabu, Pixee, Pixelfy, ShopiPixel, WeltPixel) were scanned for "bot", "spam" and "fake". **No listing claims bot filtering.** Orichi is the only multi-pixel app that does.

### Shopify itself (baseline)

Shopify sorts sessions into human or bot: "Every event that occurs on your online store … is analyzed … to determine whether the event was probably completed by a human or a bot". It leans conservative: "it's better to miss some bots than incorrectly label real customers as bots". The label applies **only to session metrics in Analytics reports**, and only to data from 7 Oct 2025 onward. The doc does not say the label reaches web pixels or apps. [help](https://help.shopify.com/en/manual/intro-to-shopify/bots/bot-filtering)

## What this means for Bot Protection

1. **Blocking in the browser is our edge.** The serious competitors filter only **Server Events**, which means a bot's **Browser Event** still reaches Meta through `fbq`/`/tr`. Orichi's single browser-side rule (Purchase without an order id) is the only browser-side filtering anyone documents. Blocking both sides, as charted, puts us ahead.
2. **On by default puts us ahead.** Littledata and Stape both make the merchant opt in.
3. **Showing counts would be new.** No vendor documents per-Market or per-reason counts or a "why was this blocked" sample. Our planned tally plus sample would be ahead of what anyone shows.
4. **Phrase claims the way the category does.** Vendors talk about outcomes ("clean data trains the algorithm", "optimize on real users instead of headless traffic", "cleaner funnel data") and avoid percentages. That fits the map's open question on the **Marketing claim**: hold back any "X% fewer junk events" until we have real numbers.
5. **Detection rules worth borrowing** (for #17/#18): Littledata's attack patterns (headless Cart/Checkout, direct posts to endpoints, steady cadence, high volume), Stape's three-band score with "watch, don't block" in the middle, Stape's 0x0-viewport signal, and Orichi's "Purchase without an order" rule. The last matches our rule that a Purchase tied to a real Shopify order is never a **Bot Event**.
6. **Be conservative about false positives.** Shopify, Littledata and Stape all say plainly that missing some bots is better than blocking a real customer.
7. **Where it sits in the plans.** Littledata includes it on every plan. Orichi, our closest competitor, puts it on its cheapest paid plan. Keeping it off our paid plans would leave us behind both.
