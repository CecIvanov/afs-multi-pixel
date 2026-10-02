// Pure Market health page logic (no I/O) so node --test covers the tile states,
// labels, summary and the pixel ID + token rules the editor enforces.

// Meta IDs are 64-bit numbers (up to 20 digits) with no fixed length; Check with Meta is the real test.
const PIXEL_ID = /^\d{1,20}$/;
const REGIONS_SHOWN = 3;
export const PIXEL_ID_HINT = "A pixel ID is digits only. Copy it from Events Manager → Data sources.";

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

export function lastEventLabel(iso, now = new Date()) {
  if (!iso) return "No events yet";
  const minutes = Math.floor((now.getTime() - new Date(iso).getTime()) / 60000);
  if (minutes < 1) return "Last event just now";
  if (minutes < 60) return `Last event ${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `Last event ${hours} h ago`;
  return `Last event ${Math.floor(hours / 24)} d ago`;
}

/** The share of the last 24 h's Browser Events that also reached Meta by server. */
export function serverShare({ browser_24h, server_24h }) {
  if (!browser_24h) return "—";
  const share = (server_24h / browser_24h) * 100;
  return `${Number.isInteger(share) ? share : share.toFixed(1)}%`;
}

/**
 * Bars for the 24-hour events-per-hour chart.
 * @param {number[]} series
 * @param {{ width: number, height: number }} box
 * @returns {{ x: number, width: number, height: number }[]}
 */
export function sparkBars(series, { width, height }) {
  const max = Math.max(...series, 1);
  const barWidth = width / series.length;
  return series.map((value, i) => ({
    x: Math.round(i * barWidth + 1),
    width: Math.max(1, Math.round(barWidth - 2)),
    height: Math.max(1, Math.round((value / max) * (height - 2))),
  }));
}

/** The setup strip (spec §4). `embedActive` is null while it's still being read. */
export function setupSteps({ embedActive, markets, setup }) {
  return [
    { key: "embed", label: "App embed", done: embedActive === true },
    { key: "pixels", label: "Pixels", done: markets.some((m) => m.pixel) },
    { key: "consent", label: "Consent", done: Boolean(setup.consent_confirmed) },
    { key: "verified", label: "Verified in Meta", done: Boolean(setup.verified_in_meta) },
  ];
}
