// Pure Markets overview and Market page logic (no I/O) so node --test covers the
// tile states, labels, summary, the pixel ID + token rules the forms enforce, and
// the Market page's figures, chart and event table.

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

/** "sending" | "token_problem" | "deactivated" | "new" | "unmapped" */
export function marketTileState(market) {
  if (market.pixel?.active === false) return "deactivated";
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

// UTC so the server render and the browser agree (no hydration mismatch).
export const formatUtc = (iso) =>
  `${new Date(iso).toLocaleString("en-GB", { timeZone: "UTC", dateStyle: "medium", timeStyle: "short" })} UTC`;

/** One banner per Market whose server events are on hold for a working token:
 * why, how many are waiting, and when the oldest is dropped (Meta's 7 days).
 * @returns {{ marketId: number, name: string, heading: string, text: string }[]} */
export function heldEventAlerts(markets, formatDate = formatUtc) {
  return markets
    .filter((m) => marketTileState(m) === "token_problem")
    .map((m) => {
      const held = m.stats?.held ?? 0;
      const reason = m.pixel?.token_error || (m.pixel?.has_token ? "Meta rejected the saved token." : "No token is saved.");
      const waiting = held
        ? `${held} server ${held === 1 ? "event is" : "events are"} waiting and will be sent once you save a working token.` +
          (m.stats?.held_until ? ` Events still waiting on ${formatDate(m.stats.held_until)} will be dropped.` : "")
        : "New server events will wait until you save a working token.";
      return {
        marketId: m.shopify_market_id,
        name: m.name,
        heading: `${m.name}: server events are on hold`,
        text: `${reason} ${waiting}`,
      };
    });
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

// --- the Market page (#15) ---------------------------------------------------------------
export const RANGES = [
  { key: "24h", label: "24 hours", long: "Last 24 hours" },
  { key: "7d", label: "7 days", long: "Last 7 days" },
  { key: "30d", label: "30 days", long: "Last 30 days" },
];
// Meta's Conversions API tokens start with EAA and run to about 200 characters.
const MIN_TOKEN_LENGTH = 150;
const LOW_REACH = 0.9;
const STATUS_LABELS = {
  sent: "Sent",
  held: "Held",
  waiting: "Waiting",
  rejected: "Rejected",
  failed: "Failed",
  skipped: "Skipped",
};
const ALWAYS_SHOWN_STATUSES = ["sent", "held", "waiting", "rejected"];

export function parseRange(value) {
  return RANGES.some((r) => r.key === value) ? value : "24h";
}

/** A warning while pasting, or null: Check with Meta is the real test. */
export function tokenWarning(value) {
  const token = String(value ?? "").trim();
  if (!token) return null;
  if (/\s/.test(token)) return "The token has spaces or line breaks in it. Copy it again from Events Manager.";
  if (!token.startsWith("EAA") || token.length < MIN_TOKEN_LENGTH) {
    return "This token looks incomplete. Copy the whole token from Events Manager: it starts with EAA and is about 200 characters.";
  }
  return null;
}

export function updatedAgo(iso, now = new Date()) {
  const minutes = Math.floor((now.getTime() - new Date(iso).getTime()) / 60000);
  if (minutes < 1) return "Updated just now";
  if (minutes < 60) return `Updated ${minutes} min ago`;
  return `Updated ${Math.floor(minutes / 60)} h ago`;
}

export function statusLabel(status) {
  return STATUS_LABELS[status] ?? status;
}

export function sharePct(part, whole) {
  if (!whole) return "—";
  return `${((part / whole) * 100).toFixed(1)}%`;
}

/**
 * Events by type: share of all events, share that reached Meta (low under 90%), bar width.
 * @param {{ browser: number, types: { event_name: string, count: number, sent: number }[] }} detail
 * @returns {{ event_name: string, count: number, share: string, reached: string, low: boolean, bar: number }[]}
 */
export function typeRows(detail) {
  const max = Math.max(1, ...detail.types.map((t) => t.count));
  return detail.types.map((t) => ({
    event_name: t.event_name,
    count: t.count,
    share: sharePct(t.count, detail.browser),
    reached: sharePct(t.sent, t.count),
    low: t.count > 0 && t.sent / t.count < LOW_REACH,
    bar: Math.round((t.count / max) * 1000) / 10,
  }));
}

export function notSentDetail({ not_sent, held, rejected }) {
  const other = not_sent - held;
  const parts = [
    held ? `${held} held` : null,
    other ? `${other} waiting or failed` : null,
    rejected ? `${rejected} refused before Meta` : null,
  ].filter(Boolean);
  return parts.length ? parts.join(" · ") : "Nothing waiting";
}

/**
 * Stacked bars as % of the tallest bucket: reached Meta, held, and the rest.
 * @param {{ sent: number, held: number, not_sent: number }[]} series
 * @returns {{ sent: number, held: number, notSent: number, total: number }[]}
 */
export function chartBars(series) {
  const totals = series.map((b) => b.sent + b.held + b.not_sent);
  const max = Math.max(...totals, 0);
  const pct = (n) => (max ? Math.round((n / max) * 1000) / 10 : 0);
  return series.map((b, i) => ({ sent: pct(b.sent), held: pct(b.held), notSent: pct(b.not_sent), total: totals[i] }));
}

export function chartAxis(range) {
  if (range === "7d") return ["7 days ago", "4 days ago", "Today"];
  if (range === "30d") return ["30 days ago", "15 days ago", "Today"];
  return ["24 h ago", "18 h", "12 h", "6 h", "Now"];
}

export function statusChips(counts) {
  const extra = Object.keys(STATUS_LABELS).filter((k) => !ALWAYS_SHOWN_STATUSES.includes(k) && counts[k]);
  return [...ALWAYS_SHOWN_STATUSES, ...extra].map((key) => ({ key, label: STATUS_LABELS[key], count: counts[key] ?? 0 }));
}

export function pageLabel({ page, page_size, total, rows }) {
  if (!total || !rows) return "No events";
  const first = (page - 1) * page_size + 1;
  return `Showing ${first}–${first + rows - 1} of ${total} events`;
}

/** The connection panel's last Check with Meta. */
export function lastCheckLabel(pixel, formatDate = formatUtc) {
  if (pixel.last_check_ok == null || !pixel.last_checked_at) return { ok: null, text: "Not checked yet" };
  const when = formatDate(pixel.last_checked_at);
  return pixel.last_check_ok
    ? { ok: true, text: `Passed · ${when}` }
    : { ok: false, text: `Refused · ${when}${pixel.last_check_error ? ` · ${pixel.last_check_error}` : ""}` };
}

/** The dataset's overview in Events Manager. Meta picks the business when the link carries none. */
export function eventsManagerUrl(pixelId) {
  return `https://eventsmanager.facebook.com/events_manager2/list/dataset/${encodeURIComponent(pixelId)}/overview`;
}

/** The grey "deactivated" notice, with any Server Events held since (7-day rule). */
export function deactivatedNote(market, formatDate = formatUtc) {
  const base =
    `No browser or server events are sent for shoppers in ${market.name}. ` +
    "The pixel ID and token stay saved, so you can turn it back on at any time.";
  const held = market.stats?.held ?? 0;
  if (!held) return base;
  return (
    `${base} ${held} server ${held === 1 ? "event is" : "events are"} held and will be sent when you reactivate, ` +
    "if Meta accepts the token." +
    (market.stats?.held_until ? ` Events still held on ${formatDate(market.stats.held_until)} will be dropped.` : "")
  );
}
