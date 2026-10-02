# Does Meta filter bot events itself, and how does dropping events affect it?

Research for issue #19, part of the Bot Protection map (#16). Terms follow `CONTEXT.md`: **Browser Event**, **Server Event**, **Relay**, **Bot Event**, **Bot Protection**.

Researched 2026-10-02. Sources are Meta's Business Help Center, Meta for Developers, and Meta's own pixel code (`fbevents.js` and the per-pixel config script) as served that day. Help Center pages were read in full. Each claim below is either quoted from a source or marked **Inference**.

## Short answer

1. **Meta filters bots for billing, not for your conversion data.** The help pages only describe invalid-traffic filtering for impressions and clicks you pay for. Nothing in Meta's documentation says Meta removes bot events from pixel or Conversions API data before reporting or optimisation.
2. **Meta's pixel code does block some bots in the browser. This is not documented.** `fbevents.js` contains a `BotBlocking` plugin. It checks the user agent against a list of about 640 crawler patterns and drops the event before `/tr` is called. It also marks headless and Selenium browsers in a bitmask, but still sends their events. This only covers events fired through `fbq`. It does not cover our checkout Web Pixel's direct `/tr` calls or the Conversions API.
3. **Dropping both copies of a Bot Event is neutral for deduplication and event coverage.** Meta only compares events it receives, so a pair that never arrives can't fail to deduplicate.
4. **Dropping only one copy is what causes side effects.** Drop only the Server Event, and the Browser Event counts as not covered, so event coverage falls toward Meta's 75% goal. Drop only the Browser Event, and the Server Event counts on its own as a conversion, which is the leak we are trying to stop. Meta's own browser-side bot blocking already causes this second case in our storefront flow (see §3).
5. **Meta gives no guidance for or against suppressing bot events.** The nearest guidance is from Traffic permissions: blocked events "aren't included in your ads performance" and "can't be recovered". This fits our decision to count Bot Events rather than quarantine them.

## 1. What Meta documents about bot and invalid traffic

| Claim | Source |
|---|---|
| "Advertisers don't pay for impressions that Meta determines to be invalid, and invalid impressions are excluded from all other reporting." Invalid traffic includes "non-human traffic we detect or other invalid traffic such as from IP addresses associated with fraud." | [Gross impressions](https://www.facebook.com/business/help/774724292709131) |
| Audience Network uses "General Invalid Traffic Detection" as defined by the MRC's invalid-traffic guidelines. | [Audience Network methodology](https://www.facebook.com/business/help/515459418788246) (search snippet only; the page did not render) |
| Traffic permissions let you set a domain **allow list** or **block list** for pixel events. "You can't recover events that were lost while a domain was blocked, and blocked events aren't included in your ads performance." | [Manage traffic permissions](https://www.facebook.com/business/help/278125336598935), [About traffic permissions](https://www.facebook.com/business/help/572690630080597) |
| Traffic permissions exist because "your pixel ID is public information" and others can fire it from their own sites. Meta emails the owner, and shows a Diagnostics warning, when a new domain sends events. | [About traffic permissions](https://www.facebook.com/business/help/572690630080597) |
| Events Manager shows events "potentially before discarding events for reasons such as duplication, data policies or regulations". Ads Manager shows attributed events after those discards. | [Differences between event counts](https://www.facebook.com/business/help/337196340694086) |
| For the Conversions API, website events need `client_user_agent`, `action_source` and `event_source_url`. Nothing on these pages describes bot filtering of server events. | [Customer information parameters](https://developers.facebook.com/documentation/ads-commerce/conversions-api/parameters/customer-information-parameters), [Dedup docs](https://developers.facebook.com/docs/marketing-api/conversions-api/deduplicate-pixel-and-server-events) |

**What we found:** Meta documents bot filtering only on the ad-delivery and billing side (impressions and clicks). For conversion events, the only filter it documents is the domain-level Traffic permissions, which works on domains and has nothing to do with bots. We found no Meta document saying that pixel or Conversions API events from bots are removed before reporting, attribution or optimisation.

## 2. What Meta's pixel code actually does (undocumented)

Source: `https://connect.facebook.net/en_US/fbevents.js` (`fbq.version="2.9.414"`, module bundle `3.32.2`) and the per-pixel config script `https://connect.facebook.net/signals/config/<pixel_id>`, both fetched 2026-10-02. To get a real config we used the pixel of a public Bulgarian store (ozone.bg, `1458212301078289`). A made-up pixel ID returned a config without the bot-blocking rules, so the rules are delivered per pixel.

### 2a. `BotBlocking` plugin: matches the user agent and drops the event

- The per-pixel config contains `fbq.loadPlugin("botblocking")` and `instance.optIn("<pixel>", "BotBlocking", true)`. It also sets `config.set("<pixel>", "botblocking", {rules: {spider_bot_rules, browser_patterns}})`. In the sample, `spider_bot_rules` has 644 lines and `browser_patterns` has 643.
- `SignalsFBEventsBotDetectionEngine.shouldBlockUserAgent(ua)` returns true in two cases:
  - the UA matches a spider pattern and none of its `~` exceptions, or
  - the UA matches none of the "known browser" patterns. Within that case, it only blocks `facebookexternalhit`.

  The mobile Facebook in-app browsers (`FBAN/`, `FBAV/`, `fb_iab`…) are always let through.
- Examples from the spider list: `googlebot`, `bingbot`, `AdsBot-Google`, `facebookexternalhit`, `HeadlessChrome/`, `python-requests/`, `Python-urllib`, `curl` (with exceptions such as `Curlings`), `wget`, `Pingdom`, `monitor`, `Siteimprove`, `archive.org`.
- **Inference:** the rule format looks like the IAB/ABC International Spiders & Bots List: `0` means "contains", `1` means "starts with", and `~` separates exceptions. Meta does not name the list.
- What happens to the event:
  - When the guardrail `bot_blocking_client_side_block_enabled` is on, the `SendEventEvent` listener returns `true` for a bot UA. It also logs `"[Meta pixel] Bot traffic detected and blocked - pixel_id: …"`, and the hit is not sent to `/tr`.
  - When the guardrail is off, the plugin instead adds a block flag `bfs: {b: 1}` to the event's custom parameters. The event is then sent but marked.
- The guardrail's setting in `fbevents.js` is `{"name":"bot_blocking_client_side_block_enabled","passRate":1,"enableForPixels":["1306783967701444"]}`. Under the guardrail's `eval` logic, `passRate: 1` turns it on for every pixel. So as of 2026-10-02, blocking is on for all pixels that are opted in.
- **Limits:** the check reads only `navigator.userAgent`. A bot that pretends to be a normal Chrome or Safari passes. It is also server-controlled and undocumented, so Meta can change or remove it at any time.

### 2b. `opttracking` flags: headless and Selenium are marked, not blocked

- `fbevents.js` checks for:
  - Selenium/WebDriver globals (`__webdriver_evaluate`, `_selenium`, `callSelenium`, …) and `webdriver`/`selenium`/`driver` attributes on `<html>`;
  - PhantomJS and Nightmare globals;
  - a `HeadlessChrome` user agent.
- The results go into the `o` bitmask sent with every hit (`IS_HEADLESS: 128`, `IS_SELENIUM: 256`, `HAS_DETECTION_FAILED: 512`). The event is still sent.
- **Inference:** Meta receives these flags and may use them on its side, but nothing documents whether flagged events are dropped from reporting or optimisation.

### 2c. What this means for our pipeline

| Path | Does Meta's bot handling apply? |
|---|---|
| Storefront Browser Event (`multi-pixel.js` calls `fbq('trackSingle', …)` through `fbevents.js`) | **Yes**: UA-list blocking plus the headless/Selenium flags. |
| Checkout Browser Event (Web Pixel `fetch('https://www.facebook.com/tr/?…')` directly, `shopify/extensions/multi-pixel-checkout/src/index.ts`) | **No.** It skips `fbevents.js`, so the plugins never run. |
| Server Event (Conversions API from `RelayService`) | **No documented filtering.** |

## 3. Deduplication: what happens when one or both copies are dropped

Meta's rules (quoted):

- "a Meta Pixel's `eventID` must match the Conversion API's `event_id`" and the event names must match. Alternatively, `event_name` plus `fbp` and/or `external_id`. ([Dev docs](https://developers.facebook.com/docs/marketing-api/conversions-api/deduplicate-pixel-and-server-events))
- "Events are only deduplicated if they are received within 48 hours of when we receive the first event with a given `event_id`." (same)
- "If server and browser events do not differ meaningfully in their content, we generally prefer the event that is received first." (same)
- The `fbp`/`external_id` method "does not deduplicate events when only using one event source." (same)
- "Deduplication not needed: You send different events from each source." ([Help: About deduplication](https://www.facebook.com/business/help/823677331451951))

What this means for each case (**Inference**, drawn from the rules above):

| We drop… | Deduplication effect | Net effect in Meta |
|---|---|---|
| **Both** copies | No pair arrives, so there is nothing to deduplicate or fail. | The Bot Event never exists in Meta. This is the cleanest option. |
| **Only the Server Event** (the Browser Event already went out) | The Browser Event is kept alone. Nothing is double-counted. | The bot conversion still counts, and coverage falls (§4). This is the worst of both. |
| **Only the Browser Event** | The Server Event is kept alone. Nothing is double-counted. | The bot conversion still counts through the Conversions API. This defeats the purpose. |

So dropping only one copy never causes double counting. It just fails to remove the Bot Event.

**Interaction with Meta's own blocking (§2a):** for a crawler UA on the storefront, `fbevents.js` drops the Browser Event, but `multi-pixel.js` still sends the Relay. The Relay becomes a Server Event that Meta receives alone and counts. **Inference:** today our app may be "recovering" bot events that Meta's pixel deliberately threw away. Bot Protection should recognise at least the same UAs that Meta's list does, so we don't recover what Meta blocked.

## 4. Event Match Quality, event coverage, ACR and diagnostics

### Event coverage

- "Event coverage is the 7-day average percent of Pixel events that are covered by the Conversions API, and share deduplication keys with events from the Conversions API." The API returns `goal_percentage: 75`, with the description "The percentage of events received from your Conversions API compared to unique browser events from the Meta Pixel." ([Dataset Quality API](https://developers.facebook.com/docs/marketing-api/conversions-api/dataset-quality-api/))
- Best practices: "Aim for a 75% event coverage ratio of Conversions API to Meta Pixel events for accurate reporting and optimal ad performance." ([Help: Conversions API best practices](https://www.facebook.com/business/help/308855623839366))
- **Inference:**
  - Dropping both copies takes the same amount out of the numerator and the denominator, so coverage stays about the same.
  - Dropping only Server Events lowers coverage, and could push it under 75% if bots are a large share.
  - Dropping only Browser Events raises the ratio artificially.

### Event Match Quality (EMQ)

- EMQ is "a score from 0 to 10 based on the quality of customer information you're sending for a specific server event and the percentage of event instances matched to Meta accounts." It applies to Conversions API website events, and "The last 48 hours of data are used to calculate scores." ([Help: About EMQ](https://www.facebook.com/business/help/765081237991954))
- **Inference:** bots rarely carry match keys such as `fbc`, a logged-in email or a stable `fbp`. Removing their Server Events should keep EMQ the same or raise it, because a larger share of what's left is matchable. There is no documented penalty for sending fewer events. EMQ is a ratio, not a volume metric. The one risk is very low volume: EMQ needs events "regularly" in the 48-hour window, and that does not apply to stores with real traffic.

### Additional Conversions Reported (ACR)

- ACR "estimates how many conversions … are measured as a result of an advertiser's Conversions API setup." ([Dataset Quality API](https://developers.facebook.com/docs/marketing-api/conversions-api/dataset-quality-api/))
- **Inference:** Server-only bot events, the leak described in §3, would inflate ACR. Blocking them may lower ACR slightly. That drop is real data being cleaned, not a loss.

### Diagnostics in Events Manager

- Diagnostics show Critical issues ("platform updates, evolving privacy regulations and Meta's Privacy Policy violations") and Warnings. Warnings cover things like a wrong value parameter or "your Meta Pixel recently started sending events from new domains". ([Help: About diagnostics](https://www.facebook.com/business/help/667164051342757))
- The deduplication help page lists "Look for unexpected spikes or drops in event counts" as a troubleshooting step and links to "Address drops in website events". ([Help: About deduplication](https://www.facebook.com/business/help/823677331451951))
- Meta also lists a help article "What to do if there's a drop in website events from the Meta Pixel" in the Events section. We could not get its ID or content.
- **Inference:**
  - If Bot Protection removes a lot of traffic when it is switched on, the merchant may see an event-volume drop, and possibly a "drop in events" notice.
  - We found no documented diagnostic that complains about missing bot events.
  - If only Server Events are dropped, the low event coverage recommendation is the one most likely to appear.

## 5. Ad optimisation

- Meta says matched, real-time events help "deliver your ads to people who are more likely to take the action you care about". ([Help: About EMQ](https://www.facebook.com/business/help/765081237991954), [Best practices](https://www.facebook.com/business/help/308855623839366))
- Meta recommends sending the same events through both the pixel and the Conversions API (a "redundant event setup") with deduplication. ([Best practices](https://www.facebook.com/business/help/308855623839366))
- **Inference:** Meta does not say how bot conversions affect optimisation. They are non-human actions sent as conversion signals. With a Purchase-optimised campaign they are rare, because a real Purchase is never a Bot Event in our rules. With upper-funnel events (ViewContent, AddToCart) they can teach delivery the wrong audience, and they inflate retargeting audiences built from those events. Removing them can only make the signal cleaner. The cost is a lower raw event count, and that count is not an optimisation input on its own.

## 6. Recommended practices and warnings about suppressing events

- Meta has **no published guidance** on suppressing bot events, and no warning against it.
- The closest Meta-documented controls are Traffic permissions (domain allow/block lists) and the pixel's own UA blocking. Both drop events silently, before reporting.
- Meta's warning about its own blocking control is that blocked events "aren't included in your ads performance" and "can't be recovered". This matches our charting decision: Bot Events are counted, not quarantined, and never released later.

## Implications for the Bot Protection spec

1. **Always block a Bot Event's Browser Event and Server Event together.** Dropping one copy leaves the bot conversion in Meta and, when the Server Event is the one dropped, lowers event coverage. On the storefront, that means deciding before `fbq` and skipping the Relay for the same event. In the checkout, it means skipping both `/tr` and the Relay.
2. **At minimum, match Meta's own UA list on the Relay path.** Otherwise we turn Browser Events that Meta blocked into Server Events. Options: check the user agent server-side against the same IAB-style patterns, or skip the Relay when `fbevents.js` blocked the event. The list is in each pixel's config script, but it is undocumented and may change.
3. **Do the checkout check ourselves.** Meta's pixel bot blocking never runs in our checkout Web Pixel because it calls `/tr` directly.
4. **Expect the merchant to see a drop in event counts in Events Manager** when Bot Protection is switched on. Our "held back" tally should explain that drop before a Meta diagnostic does.
5. **Don't promise better EMQ or ACR.** EMQ will probably stay the same or rise and ACR may fall slightly; both are inferences, not anything Meta documents.

## Sources

- Meta for Developers: [Deduplicate Pixel and Server Events](https://developers.facebook.com/docs/marketing-api/conversions-api/deduplicate-pixel-and-server-events)
- Meta for Developers: [Dataset Quality API](https://developers.facebook.com/docs/marketing-api/conversions-api/dataset-quality-api/)
- Meta for Developers: [Customer information parameters](https://developers.facebook.com/documentation/ads-commerce/conversions-api/parameters/customer-information-parameters)
- Help Center: [About deduplication for Meta Pixel and Conversions API events](https://www.facebook.com/business/help/823677331451951)
- Help Center: [About event match quality](https://www.facebook.com/business/help/765081237991954)
- Help Center: [Best practices for Conversions API](https://www.facebook.com/business/help/308855623839366)
- Help Center: [About diagnostics in Meta Events Manager](https://www.facebook.com/business/help/667164051342757)
- Help Center: [About Meta Pixel traffic permissions](https://www.facebook.com/business/help/572690630080597), [Manage traffic permissions](https://www.facebook.com/business/help/278125336598935), [Best practices for traffic permissions](https://www.facebook.com/business/help/267505221173979)
- Help Center: [Gross impressions (includes invalid and non-human traffic)](https://www.facebook.com/business/help/774724292709131)
- Help Center: [Differences between event counts](https://www.facebook.com/business/help/337196340694086)
- Code: `https://connect.facebook.net/en_US/fbevents.js` (2.9.414), modules `SignalsFBEventsBotDetectionEngine`, `SignalsFBEvents.plugins.botblocking`, `SignalsFBEventsGuardrail`, `SignalsFBEvents.plugins.opttracking`
- Code: `https://connect.facebook.net/signals/config/1458212301078289?v=2.9.250&r=stable` (a public store's pixel config, used as a sample of `botblocking` rules)
- Repo: `shopify/extensions/multi-pixel-embed/assets/multi-pixel.js` (`fbq` and the Relay), `shopify/extensions/multi-pixel-checkout/src/index.ts` (direct `/tr` and the Relay)
