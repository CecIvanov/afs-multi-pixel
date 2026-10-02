import { test } from "node:test";
import assert from "node:assert/strict";
import {
  addedAgo,
  canCheckWithMeta,
  heldEventAlerts,
  isValidPixelId,
  lastEventLabel,
  marketLabels,
  marketTileState,
  normalizePixelId,
  regionsLabel,
  serverShare,
  setupSteps,
  sparkBars,
  summarizeMarkets,
  tokenRequired,
  chartBars,
  deactivatedNote,
  eventsManagerUrl,
  chartAxis,
  lastCheckLabel,
  notSentDetail,
  pageLabel,
  parseRange,
  sharePct,
  statusChips,
  statusLabel,
  tokenWarning,
  typeRows,
  updatedAgo,
} from "./markets.shared.mjs";

const pixel = (over = {}) => ({
  pixel_id: "1290457710338842",
  pixel_name: "Dontmiss BG",
  test_event_code: null,
  token_state: "ok",
  has_token: true,
  ...over,
});
const market = (over = {}) => ({
  shopify_market_id: 101,
  name: "Bulgaria",
  market_type: "REGION",
  status: "ACTIVE",
  regions: ["Bulgaria"],
  first_seen_at: "2026-10-01T10:00:00Z",
  is_new: false,
  pixel: null,
  ...over,
});

test("a pixel ID is up to 20 digits of any length, ignoring pasted spaces", () => {
  assert.equal(isValidPixelId("1290457710338842"), true);
  assert.equal(isValidPixelId("129045771033884"), true);
  assert.equal(isValidPixelId("12904577103388421"), true);
  assert.equal(isValidPixelId("12904577103388"), true);
  assert.equal(isValidPixelId(" 1290 4577 1033 8842 "), true);
  assert.equal(isValidPixelId("123456789012345678901"), false);
  assert.equal(isValidPixelId("12904577103388a2"), false);
  assert.equal(isValidPixelId(""), false);
  assert.equal(normalizePixelId(" 1290 4577 1033 8842 "), "1290457710338842");
});

test("tile state: sending, token problem, new, or plain unmapped", () => {
  assert.equal(marketTileState(market({ pixel: pixel() })), "sending");
  assert.equal(marketTileState(market({ pixel: pixel({ token_state: "rejected" }) })), "token_problem");
  assert.equal(marketTileState(market({ pixel: pixel({ has_token: false }) })), "token_problem");
  assert.equal(marketTileState(market({ is_new: true })), "new");
  assert.equal(marketTileState(market()), "unmapped");
});

test("a deactivated pixel is its own state, whatever its token", () => {
  assert.equal(marketTileState(market({ pixel: pixel({ active: false }) })), "deactivated");
  assert.equal(marketTileState(market({ pixel: pixel({ active: false, token_state: "rejected" }) })), "deactivated");
  assert.deepEqual(heldEventAlerts([market({ pixel: pixel({ active: false, token_state: "rejected" }) })]), []);
});

test("B2B and Draft Markets are labelled", () => {
  assert.deepEqual(marketLabels(market()), []);
  assert.deepEqual(marketLabels(market({ market_type: "COMPANY_LOCATION" })), ["B2B"]);
  assert.deepEqual(marketLabels(market({ market_type: "COMPANY_LOCATION", status: "DRAFT" })), ["B2B", "Draft"]);
});

test("regions read as a short list", () => {
  assert.equal(regionsLabel([]), "");
  assert.equal(regionsLabel(["Greece", "Cyprus"]), "Greece, Cyprus");
  assert.equal(regionsLabel(["Austria", "Belgium", "Croatia", "Denmark", "Estonia"]), "Austria, Belgium, Croatia and 2 more");
});

test("summary counts Markets sending and Markets needing attention", () => {
  const ms = [
    market({ pixel: pixel() }),
    market({ pixel: pixel({ token_state: "rejected" }) }),
    market({ is_new: true }),
    market(),
  ];
  assert.deepEqual(summarizeMarkets(ms), { total: 4, sending: 1, attention: 2 });
});

test("addedAgo says when a new Market was first seen", () => {
  const now = new Date("2026-10-01T12:00:00Z");
  assert.equal(addedAgo("2026-10-01T11:59:40Z", now), "added just now");
  assert.equal(addedAgo("2026-10-01T11:15:00Z", now), "added 45 minutes ago");
  assert.equal(addedAgo("2026-10-01T10:00:00Z", now), "added 2 hours ago");
  assert.equal(addedAgo("2026-09-30T11:00:00Z", now), "added 1 day ago");
  assert.equal(addedAgo("2026-09-28T12:00:00Z", now), "added 3 days ago");
});

test("a token is required unless a good one is already saved", () => {
  assert.equal(tokenRequired(market()), true);
  assert.equal(tokenRequired(market({ pixel: pixel() })), false);
  assert.equal(tokenRequired(market({ pixel: pixel({ token_state: "rejected" }) })), true);
});

test("Check with Meta needs a valid pixel ID and a token (typed or saved)", () => {
  assert.equal(canCheckWithMeta(market(), { pixelId: "1290457710338842", token: "EAAJ..." }), true);
  assert.equal(canCheckWithMeta(market(), { pixelId: "1290457710338842", token: " " }), false);
  assert.equal(canCheckWithMeta(market(), { pixelId: "1290-4577", token: "EAAJ..." }), false);
  assert.equal(canCheckWithMeta(market({ pixel: pixel() }), { pixelId: "1290457710338842", token: "" }), true);
});

test("lastEventLabel reads like the prototype", () => {
  const now = new Date("2026-10-01T12:00:00Z");
  assert.equal(lastEventLabel(null, now), "No events yet");
  assert.equal(lastEventLabel("2026-10-01T11:59:50Z", now), "Last event just now");
  assert.equal(lastEventLabel("2026-10-01T11:58:00Z", now), "Last event 2 min ago");
  assert.equal(lastEventLabel("2026-10-01T09:00:00Z", now), "Last event 3 h ago");
});

test("serverShare is the share of Browser Events that reached Meta by server", () => {
  assert.equal(serverShare({ browser_24h: 0, server_24h: 0 }), "—");
  assert.equal(serverShare({ browser_24h: 4812, server_24h: 4790 }), "99.5%");
  assert.equal(serverShare({ browser_24h: 3, server_24h: 3 }), "100%");
});

test("sparkBars scales the 24 hourly counts into the chart box", () => {
  const bars = sparkBars([0, 5, 10, ...Array(21).fill(0)], { width: 240, height: 36 });
  assert.equal(bars.length, 24);
  assert.equal(bars[2].height, 34); // the tallest bar fills the box minus a margin
  assert.equal(bars[1].height, 17);
  assert.equal(bars[0].height, 1); // empty hours still show a hairline
  assert.equal(bars[1].x, 11);
});

test("setupSteps: embed, pixels, consent, verified in Meta", () => {
  const steps = setupSteps({
    embedActive: true,
    markets: [market({ pixel: pixel() })],
    setup: { consent_confirmed: false, verified_in_meta: false },
  });
  assert.deepEqual(
    steps.map((s) => [s.key, s.done]),
    [["embed", true], ["pixels", true], ["consent", false], ["verified", false]],
  );
  assert.equal(setupSteps({ embedActive: null, markets: [], setup: {} })[0].done, false);
});

test("held-event banners: one per Market on hold, with the count and the drop time", () => {
  const reason = "This token can't send to this pixel. Check the pixel ID, or generate the token from this pixel's settings.";
  const greece = market({
    shopify_market_id: 102,
    name: "Greece",
    pixel: pixel({ token_state: "rejected", token_error: reason }),
    stats: { held: 3, held_until: "2026-10-09T10:29:33Z" },
  });
  const sending = market({ pixel: pixel(), stats: { held: 0, held_until: null } });

  assert.deepEqual(heldEventAlerts([sending, greece], (iso) => `<${iso}>`), [
    {
      marketId: 102,
      name: "Greece",
      heading: "Greece: server events are on hold",
      text: `${reason} 3 server events are waiting and will be sent once you save a working token. Events still waiting on <2026-10-09T10:29:33Z> will be dropped.`,
    },
  ]);
  const quiet = market({ pixel: pixel({ token_state: "rejected", token_error: null }), stats: { held: 0, held_until: null } });
  assert.equal(heldEventAlerts([quiet])[0].text, "Meta rejected the saved token. New server events will wait until you save a working token.");
  const one = market({ pixel: pixel({ token_state: "rejected", token_error: "Expired." }), stats: { held: 1, held_until: null } });
  assert.equal(heldEventAlerts([one])[0].text, "Expired. 1 server event is waiting and will be sent once you save a working token.");
});

// --- the Market page (#15) ---------------------------------------------------------------
const WHOLE_TOKEN = `EAA${"x".repeat(197)}`;

test("tokenWarning flags a pasted token that doesn't look whole", () => {
  assert.equal(tokenWarning(""), null);
  assert.equal(tokenWarning(WHOLE_TOKEN), null);
  assert.equal(tokenWarning(`  ${WHOLE_TOKEN}  `), null);
  assert.match(tokenWarning(WHOLE_TOKEN.slice(0, 120)), /incomplete/);
  assert.match(tokenWarning(`EAB${"x".repeat(197)}`), /starts with EAA/);
  assert.match(tokenWarning(`EAA${"x".repeat(100)} ${"x".repeat(100)}`), /spaces or line breaks/);
});

test("updatedAgo says how fresh the figures are", () => {
  const now = new Date("2026-10-02T12:00:00Z");
  assert.equal(updatedAgo("2026-10-02T11:59:40Z", now), "Updated just now");
  assert.equal(updatedAgo("2026-10-02T11:57:00Z", now), "Updated 3 min ago");
  assert.equal(updatedAgo("2026-10-02T09:00:00Z", now), "Updated 3 h ago");
});

test("statuses read as words, and paused is Held", () => {
  assert.equal(statusLabel("held"), "Held");
  assert.equal(statusLabel("sent"), "Sent");
  assert.equal(statusLabel("waiting"), "Waiting");
  assert.equal(statusLabel("rejected"), "Rejected");
  assert.equal(statusLabel("whatever"), "whatever");
});

test("parseRange accepts 24h, 7d and 30d and defaults to 24h", () => {
  assert.equal(parseRange("7d"), "7d");
  assert.equal(parseRange("30d"), "30d");
  assert.equal(parseRange("1y"), "24h");
  assert.equal(parseRange(null), "24h");
});

test("sharePct has one decimal, and a dash when there is nothing to share", () => {
  assert.equal(sharePct(1, 3), "33.3%");
  assert.equal(sharePct(2, 2), "100.0%");
  assert.equal(sharePct(0, 0), "—");
});

test("typeRows: share of all events, share that reached Meta, low under 90%", () => {
  const rows = typeRows({
    browser: 20,
    types: [
      { event_name: "PageView", count: 10, sent: 10 },
      { event_name: "AddToCart", count: 10, sent: 8 },
    ],
  });
  assert.deepEqual(
    rows.map((r) => [r.event_name, r.share, r.reached, r.low, r.bar]),
    [
      ["PageView", "50.0%", "100.0%", false, 100],
      ["AddToCart", "50.0%", "80.0%", true, 100],
    ],
  );
});

test("notSentDetail splits held from waiting and refused", () => {
  assert.equal(notSentDetail({ not_sent: 5, held: 3, rejected: 1 }), "3 held · 2 waiting or failed · 1 refused before Meta");
  assert.equal(notSentDetail({ not_sent: 0, held: 0, rejected: 0 }), "Nothing waiting");
});

test("chartBars stacks reached, held and other per bucket against the tallest", () => {
  const bars = chartBars([
    { sent: 3, held: 1, not_sent: 0 },
    { sent: 1, held: 0, not_sent: 1 },
  ]);
  assert.deepEqual(bars, [
    { sent: 75, held: 25, notSent: 0, total: 4 },
    { sent: 25, held: 0, notSent: 25, total: 2 },
  ]);
  assert.deepEqual(chartBars([{ sent: 0, held: 0, not_sent: 0 }]), [{ sent: 0, held: 0, notSent: 0, total: 0 }]);
});

test("chartAxis labels hours for a day and days otherwise", () => {
  assert.deepEqual(chartAxis("24h"), ["24 h ago", "18 h", "12 h", "6 h", "Now"]);
  assert.deepEqual(chartAxis("7d"), ["7 days ago", "4 days ago", "Today"]);
  assert.deepEqual(chartAxis("30d"), ["30 days ago", "15 days ago", "Today"]);
});

test("statusChips: Sent, Held, Waiting, Rejected always, others when present", () => {
  assert.deepEqual(statusChips({ sent: 4, failed: 1 }), [
    { key: "sent", label: "Sent", count: 4 },
    { key: "held", label: "Held", count: 0 },
    { key: "waiting", label: "Waiting", count: 0 },
    { key: "rejected", label: "Rejected", count: 0 },
    { key: "failed", label: "Failed", count: 1 },
  ]);
});

test("pageLabel says which events are shown", () => {
  assert.equal(pageLabel({ page: 1, page_size: 50, total: 312, rows: 50 }), "Showing 1–50 of 312 events");
  assert.equal(pageLabel({ page: 7, page_size: 50, total: 312, rows: 12 }), "Showing 301–312 of 312 events");
  assert.equal(pageLabel({ page: 1, page_size: 50, total: 0, rows: 0 }), "No events");
});

test("lastCheckLabel: passed or refused, with when", () => {
  const fmt = () => "2 Oct 2026, 13:58 UTC";
  assert.deepEqual(lastCheckLabel(pixel({ last_check_ok: true, last_checked_at: "x" }), fmt), {
    ok: true,
    text: "Passed · 2 Oct 2026, 13:58 UTC",
  });
  assert.deepEqual(
    lastCheckLabel(pixel({ last_check_ok: false, last_check_error: "Bad token", last_checked_at: "x" }), fmt),
    { ok: false, text: "Refused · 2 Oct 2026, 13:58 UTC · Bad token" },
  );
  assert.deepEqual(lastCheckLabel(pixel({ last_check_ok: null, last_checked_at: null }), fmt), {
    ok: null,
    text: "Not checked yet",
  });
});

test("deactivatedNote says what is held and when it drops", () => {
  const off = (stats) => market({ name: "Greece", pixel: pixel({ active: false }), stats });
  assert.equal(
    deactivatedNote(off({ held: 0, held_until: null })),
    "No browser or server events are sent for shoppers in Greece. The pixel ID and token stay saved, so you can turn it back on at any time.",
  );
  assert.equal(
    deactivatedNote(off({ held: 2, held_until: "2026-10-09T10:29:33Z" }), (iso) => `<${iso}>`),
    "No browser or server events are sent for shoppers in Greece. The pixel ID and token stay saved, so you can turn it back on at any time. " +
      "2 server events are held and will be sent when you reactivate, if Meta accepts the token. Events still held on <2026-10-09T10:29:33Z> will be dropped.",
  );
});

test("eventsManagerUrl opens the dataset's overview", () => {
  assert.equal(
    eventsManagerUrl("1134226218952173"),
    "https://eventsmanager.facebook.com/events_manager2/list/dataset/1134226218952173/overview",
  );
});
