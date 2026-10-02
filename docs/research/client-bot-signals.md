# Research: bot signals the storefront and checkout scripts can read before firing

Ticket: #17 (map: #16, Bot Protection). Researched 2026-10-02.

## Question

Before `fbq` (theme embed, `multi-pixel.js`) or the `/tr` fetch (checkout Web Pixel, strict sandbox) fires, which bot or automation signals can each script read? How reliable is each one, what does it cost in storefront performance, and does Shopify policy restrict any of them?

## Answer in brief

- **The two scripts can see very different amounts.** The theme embed runs in the page and can read everything a page can: `navigator.webdriver`, the full user agent, `document.prerendering`, `isTrusted` on real input events, and timing. The strict Web Pixel cannot read `navigator.webdriver` at all. All it gets from Shopify is the user agent, the languages, `cookieEnabled`, window and screen sizes, scroll position, and event timestamps.
- **Only a few signals are both cheap and reliable enough to block on:** a self-declared crawler or `HeadlessChrome` user agent, and `navigator.webdriver === true` (storefront only). They catch honest bots and default automation setups. They do not catch a bot built to evade detection, because every client-side value can be spoofed.
- **Performance cost is close to zero** for property reads and a user-agent regex: no network calls, under a millisecond. Waiting for human interaction before PageView is the one costly option. It delays events and drops real bounces, so it should not gate PageView.
- **Policy:** no Shopify App Store requirement or API Terms clause mentions fingerprinting by name. Shopify's own docs say the strict sandbox exists so pixels *cannot* fingerprint, and that only the listed globals are guaranteed. Two constraints apply: (1) Built for Shopify 2.2.1 says the Lighthouse score may drop by at most 10 points; (2) API Terms 6.3 requires ePrivacy and GDPR compliance, and EDPB guidance puts JavaScript reads of device information in scope of Art. 5(3). Both scripts already run only after marketing consent, which covers these reads. Whether that consent also covers using the reads for bot detection is a question for the "bot evidence and privacy" item in #16.
- **Shopify classifies bot sessions itself, but apps can't get the verdict at event time.** It is only available afterwards, through ShopifyQL (see below).

## What each script can read

### Theme embed (`multi-pixel.js`, full page context, loaded `defer` from the app embed block)

| Signal | How to read it | What it catches | Reliability | Cost |
|---|---|---|---|---|
| `navigator.webdriver` | `navigator.webdriver === true` | WebDriver/Marionette sessions, Chrome launched with `--enable-automation`, `--headless`, or `--remote-debugging-port=0` [MDN-webdriver] | High precision: a real shopper never has it set. Low recall: stealth tools patch it or launch without those flags. | One property read |
| Headless or crawler user agent | `navigator.userAgent` matched against `HeadlessChrome` and a crawler list such as `isbot` | Crawlers that identify themselves (Googlebot, AdsBot, monitoring tools) and default headless Chrome [isbot], [ua-headless] | High precision for honest bots. `isbot`'s own fallback-pattern figures: "1% false positive and 75% bot coverage". Trivially spoofed. | Regex test, a few KB if a list is bundled |
| `navigator.userAgentData.brands` | Client Hints (Chromium, secure context) | A `HeadlessChrome` brand in some headless builds | Not Baseline: missing in Safari and Firefox [MDN-uadata]. Use only as an extra signal. | One property read |
| `document.prerendering` | true while the page is being speculatively prerendered | Not bots: pages the shopper may never view [MDN-prerender] | Exact | One property read. The fix is to defer firing until `prerenderingchange`, not to block. |
| Interaction with `isTrusted` | wait for a `pointerdown`/`scroll`/`keydown` with `event.isTrusted` | Scripts that call `element.click()` or `dispatchEvent` (both give `isTrusted === false`) [MDN-isTrusted] | Weak. Input sent through WebDriver or CDP is trusted, and many real shoppers bounce without any interaction. | Waiting delays or loses events. Not suitable for gating PageView. |
| Timing | e.g. ms from script start to the first event, or time between events | Pages driven faster than any human | Medium as a supporting signal. Thresholds need real data (shadow mode). | Negligible |
| Window shape | `outerWidth/outerHeight === 0`, empty `navigator.languages` | Older `chrome-headless-shell` style environments | Low. New headless Chrome is the real Chrome binary, and the old mode now ships separately as `chrome-headless-shell` (since Chrome 132) [chrome-headless]. | Negligible |

### Checkout Web Pixel (`multi-pixel-checkout`, `runtime_context = "strict"`)

The strict sandbox is a web worker. Shopify only guarantees `self`, `console`, timers and `fetch`/`Headers`/`Request`/`Response`, and says: "You must not rely on any other globals being available." There is no DOM, and fingerprinting by scraping the DOM is ruled out by design [shopify-pixels]. What the pixel gets comes from Shopify, as a snapshot of the top frame:

| Source | Fields (from `@shopify/web-pixels-extension` 2.18.0 types, `PixelEvents/index.d.ts`) |
|---|---|
| `init.context.navigator` and `event.context.navigator` (`WebPixelsNavigator`) | `cookieEnabled`, `language`, `languages`, `userAgent`. **Nothing else.** |
| `init.context.window` (`WebPixelsWindow`) | `innerWidth/Height`, `outerWidth/Height`, `screen.width/height`, `screenX/Y`, `scrollX/Y`, `pageX/YOffset`, `origin`, `location` |
| `init.context.document` | `location`, `referrer`, `characterSet`, `title` |
| Every event | `timestamp` (ISO 8601), `seq`, `clientId` [shopify-page-viewed] |
| `browser.cookie / localStorage / sessionStorage` | Async reads from the top frame [shopify-wpapi] |
| DOM events `clicked`, `input_*`, `form_submitted` | Mouse coordinates and the element, on "Storefront, Checkout and Thank you pages" [shopify-dom-events]. They carry no `context`. The docs do not say whether app pixels receive them. The `advanced_dom_*` events need the `read_advanced_dom_pixel_events` scope, and App Store requirement 3.2.4 says an app must "demonstrate the need for this scope". |

The checkout pixel **cannot read `navigator.webdriver`.** The `context.navigator` snapshot does not include it. The WebDriver spec also says `NavigatorAutomationInformation` "should not be exposed on `WorkerNavigator`" [webdriver-spec], and `WorkerNavigator` has no `webdriver` property [MDN-workernav]. `self.navigator.userAgent` usually exists in a worker, but Shopify does not guarantee it. Use `event.context.navigator.userAgent` instead.

So the checkout pixel can use:
1. **User agent** (`HeadlessChrome` or crawler match). This is the same test as on the storefront.
2. **Window shape** (e.g. `outerWidth === 0`, or a viewport larger than the screen). Weak.
3. **Timing across events** within one pixel instance, e.g. AddToCart arriving within milliseconds of `page_viewed`. Weak to medium. Thresholds need shadow data.
4. **A verdict passed from the storefront** through a first-party cookie. The pixel already reads `_mpx_market` this way with `browser.cookie.get`. The embed could write, say, `_mpx_bot=webdriver` and the pixel would honour it. This carries the strongest storefront-only signal (`webdriver`) into AddToCart, InitiateCheckout and AddPaymentInfo. Caveat: a bot can open checkout without loading a storefront page, and then the cookie is absent. This choice belongs to #21 (where the decision is made).

Purchase needs no client-side check. By the glossary, a Purchase tied to a real Shopify order is never a Bot Event.

## What Shopify already does about bots, and what it exposes

- Shopify labels every online store session as human or bot. It analyses "every event that occurs on your online store", and the classification is deliberately conservative: "better to miss some bots than incorrectly label real customers as bots". Filtering applies "only to sessions-related metrics", from 2025-10-07 onwards [shopify-bot-filtering]. The criteria are not published.
- Apps can read the verdict only through the ShopifyQL `human_or_bot_session` dimension, after the fact. A developer request (2026-09-23) to expose it on pixel events or in `init.context` has no staff answer [community-37926]. **No Shopify bot verdict is available before firing.**
- The help centre's "signs of bot activity" list is about order, checkout and session patterns, for example sessions from AWS or GCP data centres, or search terms that look like request IDs [shopify-identifying-bots]. The scripts can't see these. They belong to the server side (#18).

## Policy

| Source | What it says | What it means for us |
|---|---|---|
| Shopify Web Pixels docs [shopify-pixels] | Strict sandbox, guaranteed globals only, no DOM, "No fingerprinting" by design | Use only `init` and `event.context`. Do not probe `self.navigator` for extra entropy. |
| App Store requirements [app-store-req] | No clause about fingerprinting, device data or Lighthouse. 1.1: apps must be "privacy-safe, operating within—not around—Shopify's core systems". 3.2.4: the advanced DOM scope must be justified. 4.3.3/4.3.4: "Do not use any statistics or data in your app's listing content". | Avoid the advanced DOM scope. The marketing claim in #16 ("X% fewer junk events") may not belong in the listing at all. |
| Built for Shopify 2.2.1 [bfs-req] | "Your app must not reduce the storefront Lighthouse performance score by more than ten points." | Synchronous property reads and a regex are well within this. Don't add a third-party bot-detection SDK to the storefront. |
| API Terms §6.3 (updated 2026-02-27) [api-terms] | Comply with GDPR and the ePrivacy Directive. "only use the approved pixels, tags, or other forms of tracking technologies made available by Shopify" | Signals must come from our existing theme embed and Web Pixel, not a new tag. |
| EDPB Guidelines 2/2023 v2 (Oct 2024) [edpb] | Fingerprinting falls within Art. 5(3) ePD. JavaScript that tells the browser to send device information is access in scope. | Reads happen only after marketing and sale-of-data consent, since both scripts are consent-gated. Whether storing them as bot evidence needs a privacy-policy update is #16's open "bot evidence and privacy" item. |

## Recommendation for the spec (input to #21)

1. **Block client-side on high-precision signals only:** `navigator.webdriver === true` (storefront), a `HeadlessChrome` user agent, and a self-declared crawler user agent (both scripts). Reason codes: `webdriver`, `headless_ua`, `crawler_ua`.
2. **Defer during prerender** (`document.prerendering`) instead of counting it as a bot.
3. **Record weak signals without blocking** (timing, window shape, no interaction) in shadow mode, and decide on thresholds from data.
4. **Carry the storefront verdict to the Web Pixel** in a first-party cookie, following the `_mpx_market` pattern. Treat a missing cookie as "no verdict", not as "bot".
5. **Never gate PageView on interaction.**
6. Expect client-side checks to catch honest and lazy bots only. Evasive bots have to be caught server-side (#18) or not at all.

## Sources

- [MDN-webdriver] https://developer.mozilla.org/en-US/docs/Web/API/Navigator/webdriver
- [webdriver-spec] https://w3c.github.io/webdriver/#interface (NavigatorAutomationInformation, "should not be exposed on WorkerNavigator")
- [MDN-workernav] https://developer.mozilla.org/en-US/docs/Web/API/WorkerNavigator
- [MDN-uadata] https://developer.mozilla.org/en-US/docs/Web/API/Navigator/userAgentData
- [MDN-isTrusted] https://developer.mozilla.org/en-US/docs/Web/API/Event/isTrusted
- [MDN-prerender] https://developer.mozilla.org/en-US/docs/Web/API/Document/prerendering
- [chrome-headless] https://developer.chrome.com/docs/chromium/headless
- [ua-headless] Secondary sources, because the Chromium docs don't state the UA token: https://github.com/grafana/xk6-browser/issues/1497, https://github.com/captivus/chrome-agent/issues/12 (`--headless` sends `HeadlessChrome/<ver>`; can be overridden with `--user-agent`)
- [isbot] https://github.com/omrilotan/isbot (Unlicense; covers "good bots" only)
- [shopify-pixels] https://shopify.dev/docs/apps/build/marketing-analytics/pixels
- [shopify-wpapi] https://shopify.dev/docs/api/web-pixels-api
- [shopify-page-viewed] https://shopify.dev/docs/api/web-pixels-api/standard-events/page_viewed
- [shopify-dom-events] https://shopify.dev/docs/api/web-pixels-api/dom-events
- Type definitions: `shopify/node_modules/@shopify/web-pixels-extension/build/ts/types/PixelEvents/index.d.ts` (v2.18.0): `Context`, `WebPixelsNavigator`, `WebPixelsWindow`, `MouseEventData`; `RegisterInit.d.ts`
- [shopify-bot-filtering] https://help.shopify.com/en/manual/intro-to-shopify/bots/bot-filtering
- [shopify-identifying-bots] https://help.shopify.com/en/manual/intro-to-shopify/bots/identifying-bot-activity
- [community-37926] https://community.shopify.dev/t/will-the-bot-human-session-verdict-be-available-to-apps-outside-shopifyql/37926
- [app-store-req] https://shopify.dev/docs/apps/launch/shopify-app-store/app-store-requirements
- [bfs-req] https://shopify.dev/docs/apps/launch/built-for-shopify/requirements
- [api-terms] https://www.shopify.com/legal/api-terms
- [edpb] https://www.edpb.europa.eu/system/files/documents/2024-10/edpb_guidelines_202302_technical_scope_art_53_eprivacydirective_v2_en_0.pdf
- Code read: `shopify/extensions/multi-pixel-embed/assets/multi-pixel.js`, `shopify/extensions/multi-pixel-embed/blocks/multi-pixel.liquid` (script loaded `defer`), `shopify/extensions/multi-pixel-checkout/src/index.ts`, `shopify/extensions/multi-pixel-checkout/shopify.extension.toml`
