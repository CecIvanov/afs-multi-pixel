// Pure Market health page logic (no I/O) so node --test covers the tile states,
// labels, summary and the pixel ID + token rules the editor enforces.

const PIXEL_ID = /^\d{15,16}$/;
const REGIONS_SHOWN = 3;
export const PIXEL_ID_HINT = "A pixel ID is 15 or 16 digits. Copy it from Events Manager → Data sources.";

/** Pasted pixel IDs often carry spaces; Meta's IDs are digits only. */
export function normalizePixelId(value) {
  return String(value ?? "").replace(/\s/g, "");
}

export function isValidPixelId(value) {
  return PIXEL_ID.test(normalizePixelId(value));
}

/** "sending" | "token_problem" | "new" | "unmapped" */
export function marketTileState(market) {
  if (market.pixel) {
    return market.pixel.token_state === "ok" && market.pixel.has_token ? "sending" : "token_problem";
  }
  return market.is_new ? "new" : "unmapped";
}

/** B2B and Draft Markets are labelled and otherwise ordinary (spec §4). */
export function marketLabels(market) {
  const labels = [];
  if (market.market_type === "COMPANY_LOCATION") labels.push("B2B");
  if (market.status === "DRAFT") labels.push("Draft");
  return labels;
}

export function regionsLabel(regions) {
  const list = regions ?? [];
  if (list.length <= REGIONS_SHOWN + 1) return list.join(", ");
  return `${list.slice(0, REGIONS_SHOWN).join(", ")} and ${list.length - REGIONS_SHOWN} more`;
}

export function summarizeMarkets(markets) {
  const states = markets.map(marketTileState);
  return {
    total: markets.length,
    sending: states.filter((s) => s === "sending").length,
    attention: states.filter((s) => s === "token_problem" || s === "new").length,
  };
}

export function addedAgo(iso, now = new Date()) {
  const minutes = Math.floor((now.getTime() - new Date(iso).getTime()) / 60000);
  const plural = (n, unit) => `added ${n} ${unit}${n === 1 ? "" : "s"} ago`;
  if (minutes < 1) return "added just now";
  if (minutes < 60) return plural(minutes, "minute");
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return plural(hours, "hour");
  return plural(Math.floor(hours / 24), "day");
}

/** A blank token keeps the saved one, unless there is none or Meta rejected it. */
export function tokenRequired(market) {
  return !market.pixel || !market.pixel.has_token || market.pixel.token_state !== "ok";
}

export function canCheckWithMeta(market, { pixelId, token }) {
  const hasToken = String(token ?? "").trim().length > 0 || !tokenRequired(market);
  return isValidPixelId(pixelId) && hasToken;
}
