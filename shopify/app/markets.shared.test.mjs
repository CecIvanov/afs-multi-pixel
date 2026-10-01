import { test } from "node:test";
import assert from "node:assert/strict";
import {
  addedAgo,
  canCheckWithMeta,
  isValidPixelId,
  marketLabels,
  marketTileState,
  normalizePixelId,
  regionsLabel,
  summarizeMarkets,
  tokenRequired,
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

test("a pixel ID is 15 or 16 digits, ignoring pasted spaces", () => {
  assert.equal(isValidPixelId("1290457710338842"), true);
  assert.equal(isValidPixelId("129045771033884"), true);
  assert.equal(isValidPixelId(" 1290 4577 1033 8842 "), true);
  assert.equal(isValidPixelId("12904577103388"), false);
  assert.equal(isValidPixelId("12904577103388421"), false);
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
  assert.equal(canCheckWithMeta(market(), { pixelId: "123", token: "EAAJ..." }), false);
  assert.equal(canCheckWithMeta(market({ pixel: pixel() }), { pixelId: "1290457710338842", token: "" }), true);
});
