import { useEffect, useState } from "react";
import type { HeadersFunction, ActionFunctionArgs, LoaderFunctionArgs, ShouldRevalidateFunction } from "react-router";
import { boundary } from "@shopify/shopify-app-react-router/server";
import { Link, useFetcher, useLoaderData, useNavigate } from "react-router";
import { authenticate } from "../shopify.server";
import {
  checkMarketPixel,
  getMarketPage,
  listMarketEvents,
  recheckMarketPixel,
  removeMarketPixel,
  saveMarketPixel,
  setMarketPixelActive,
  type EventPageRecord,
  type MarketDetailRecord,
  type MarketRecord,
  type PixelCheckRecord,
  type RangeKey,
} from "../backend.server";
import { BackendRequestError } from "../backend-fetch.helpers.mjs";
import { withRequestContext } from "../request-context.server";
import { RefreshButton } from "../components/refresh-button";
import {
  canCheckWithMeta,
  deactivatedNote,
  chartAxis,
  chartBars,
  eventsManagerUrl,
  formatUtc,
  heldEventAlerts,
  isValidPixelId,
  lastCheckLabel,
  marketLabels,
  marketTileState,
  normalizePixelId,
  notSentDetail,
  pageLabel,
  parseRange,
  PIXEL_ID_HINT,
  RANGES,
  regionsLabel,
  sharePct,
  statusChips,
  statusLabel,
  tokenRequired,
  tokenWarning,
  typeRows,
} from "../markets.shared.mjs";
import styles from "../markets.module.css";

const NUMBER = new Intl.NumberFormat("en-US");
const fmt = (n: number) => NUMBER.format(n);

export const loader = async ({ request, params }: LoaderFunctionArgs) => {
  const { session } = await authenticate.admin(request);
  const marketId = Number(params.marketId);
  if (!Number.isSafeInteger(marketId) || marketId <= 0) throw new Response("Not found", { status: 404 });
  const search = new URL(request.url).searchParams;
  const query = {
    range: parseRange(search.get("range")) as RangeKey,
    event: search.get("event") ?? "",
    status: search.get("status") ?? "",
    q: search.get("q") ?? "",
    page: Math.max(1, Number(search.get("page")) || 1),
  };
  return withRequestContext(request, session.shop, async () => {
    try {
      const [page, events] = await Promise.all([
        getMarketPage(session.shop, marketId, query.range),
        listMarketEvents(session.shop, marketId, query),
      ]);
      return { ...page, events, query, loadedAt: new Date().toISOString() };
    } catch (error) {
      if (error instanceof BackendRequestError && error.status === 404) {
        throw new Response("This Market isn't in your store", { status: 404 });
      }
      throw error;
    }
  });
};

type ActionResult =
  | { intent: "check"; checkedFor: string; check: PixelCheckRecord }
  | { intent: "recheck"; check: PixelCheckRecord }
  | { intent: "save"; ok: true; activated: boolean }
  | { intent: "deactivate" | "reactivate" | "remove"; ok: true }
  | { intent: "save" | "remove"; ok: false; error: string };

export const action = async ({ request, params }: ActionFunctionArgs): Promise<ActionResult> => {
  const { session } = await authenticate.admin(request);
  const marketId = Number(params.marketId);
  const form = await request.formData();
  const intent = String(form.get("intent"));
  const input = {
    pixel_id: normalizePixelId(form.get("pixelId")),
    token: String(form.get("token") ?? "").trim(),
    test_event_code: String(form.get("testEventCode") ?? "").trim(),
  };
  return withRequestContext(request, session.shop, async () => {
    switch (intent) {
      case "check":
        return {
          intent,
          checkedFor: checkKey(input.pixel_id, input.token),
          check: await checkMarketPixel(session.shop, marketId, input),
        };
      case "recheck":
        return { intent, check: await recheckMarketPixel(session.shop, marketId) };
      case "deactivate":
      case "reactivate":
        await setMarketPixelActive(session.shop, marketId, intent === "reactivate");
        return { intent, ok: true };
    }
    const save = intent === "save";
    try {
      if (save) await saveMarketPixel(session.shop, marketId, input);
      else await removeMarketPixel(session.shop, marketId);
      return save ? { intent: "save", ok: true, activated: form.get("activate") === "1" } : { intent: "remove", ok: true };
    } catch (error) {
      if (error instanceof BackendRequestError && (error.status === 422 || error.status === 404)) {
        return { intent: save ? "save" : "remove", ok: false, error: error.detail };
      }
      throw error;
    }
  });
};

// A check of typed values only answers the form; it must not reload the page.
export const shouldRevalidate: ShouldRevalidateFunction = ({ formData, defaultShouldRevalidate }) =>
  formData?.get("intent") === "check" ? false : defaultShouldRevalidate;

function checkKey(pixelId: string, token: string) {
  return `${normalizePixelId(pixelId)}\n${token.trim()}`;
}

type Query = ReturnType<typeof useLoaderData<typeof loader>>["query"];

/** The page's URL with some filters changed; any filter change goes back to page 1. */
function withQuery(query: Query, changes: Partial<Query>) {
  const next = { ...query, page: 1, ...changes };
  const params = new URLSearchParams();
  if (next.range !== "24h") params.set("range", next.range);
  if (next.event) params.set("event", next.event);
  if (next.status) params.set("status", next.status);
  if (next.q) params.set("q", next.q);
  if (next.page > 1) params.set("page", String(next.page));
  return `?${params}`;
}

/** The Market page (#15): figures, the pixel and Conversions API connection, and
 * the events of one Market. A Market without a pixel opens in connect mode. */
export default function MarketPage() {
  const { market, detail, events, query, loadedAt } = useLoaderData<typeof loader>();
  // Keyed so the "now sending" banner outlives the connect form it came from.
  const activation = useFetcher<ActionResult>({ key: `activate-${market.shopify_market_id}` });
  const activated = activation.data?.intent === "save" && activation.data.ok && activation.data.activated;

  return (
    <s-page heading={market.name} inlineSize="large">
      <s-stack gap="base">
        <nav aria-label="Breadcrumb" className={styles.crumbs}>
          <Link to="/app">Markets</Link>
          <span aria-hidden="true">/</span>
          <span>{market.name}</span>
        </nav>
        {market.pixel ? (
          <ConfiguredMarket
            market={market}
            detail={detail}
            events={events}
            query={query}
            loadedAt={loadedAt}
            activated={Boolean(activated)}
          />
        ) : (
          <ConnectMode market={market} fetcher={activation} />
        )}
      </s-stack>
    </s-page>
  );
}

const BADGE = {
  sending: { tone: "success", label: "Sending" },
  token_problem: { tone: "critical", label: "Token problem" },
  deactivated: { tone: "neutral", label: "Deactivated" },
} as const;

function MarketHeader({ market, loadedAt }: { market: MarketRecord; loadedAt?: string }) {
  const state = marketTileState(market);
  const badge = BADGE[state as keyof typeof BADGE] ?? { tone: "neutral", label: "Not configured" };
  const facts = [regionsLabel(market.regions), ...marketLabels(market).map((l) => `${l} Market`)].filter(Boolean);
  return (
    <div className={styles.header}>
      <div className={styles.titleBlock}>
        <div className={styles.titleRow}>
          <h1 className={styles.title}>{market.name}</h1>
          <s-badge tone={badge.tone}>{badge.label}</s-badge>
        </div>
        <div className={styles.subtitle}>
          {facts.join(" · ")}
          {market.pixel ? (
            <>
              {facts.length ? " · " : ""}Pixel <span className={styles.monoDark}>{market.pixel.pixel_id}</span>
            </>
          ) : null}
        </div>
      </div>
      {loadedAt ? (
        <s-stack direction="inline" gap="small-200" alignItems="center">
          <RefreshButton loadedAt={loadedAt} />
          {market.pixel ? (
            <s-button href={eventsManagerUrl(market.pixel.pixel_id)} target="_blank">
              View in Events Manager
            </s-button>
          ) : null}
        </s-stack>
      ) : null}
    </div>
  );
}

function ConnectionBadge({ market }: { market: MarketRecord }) {
  const badge = BADGE[marketTileState(market) as keyof typeof BADGE];
  return badge ? <s-badge tone={badge.tone}>{badge.label}</s-badge> : null;
}

function ConfiguredMarket({
  market,
  detail,
  events,
  query,
  loadedAt,
  activated,
}: {
  market: MarketRecord;
  detail: MarketDetailRecord;
  events: EventPageRecord;
  query: Query;
  loadedAt: string;
  activated: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const stateFetcher = useFetcher<ActionResult>();
  const [held] = heldEventAlerts([market]);
  const deactivated = marketTileState(market) === "deactivated";
  const range = RANGES.find((r) => r.key === query.range) ?? RANGES[0];
  const startEdit = () => {
    setEditing(true);
    document.getElementById("connection")?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <>
      <MarketHeader market={market} loadedAt={loadedAt} />

      {activated ? (
        <s-banner tone="success" heading={`${market.name} is now sending`}>
          Browser and server events for shoppers in this Market go to pixel {market.pixel?.pixel_id}. Events show up
          on this page within a few minutes of shopper activity.
        </s-banner>
      ) : null}
      {held ? (
        <s-banner tone="critical" heading="Server events are on hold">
          {held.text}
          <s-button slot="secondary-actions" onClick={startEdit}>
            Update token
          </s-button>
        </s-banner>
      ) : null}
      {deactivated ? (
        // Grey, not a Polaris banner tone: deactivating is the merchant's choice, not a problem.
        <section className={styles.notice} aria-labelledby="deactivated-h">
          <div className={styles.grow}>
            <b id="deactivated-h">This pixel is deactivated</b>
            <div>{deactivatedNote(market)}</div>
          </div>
          <s-button
            variant="primary"
            loading={stateFetcher.state !== "idle"}
            onClick={() => stateFetcher.submit({ intent: "reactivate" }, { method: "post" })}
          >
            Reactivate
          </s-button>
        </section>
      ) : null}

      <div className={styles.rangeRow}>
        <div role="group" aria-label="Time range" className={styles.segments}>
          {RANGES.map((r) => (
            <Link
              key={r.key}
              to={withQuery(query, { range: r.key as RangeKey })}
              className={styles.segment}
              aria-current={r.key === query.range ? "true" : undefined}
              preventScrollReset
            >
              {r.label}
            </Link>
          ))}
        </div>
        <s-text color="subdued">{range.long} · Counts include every event the storefront relayed for this Market</s-text>
      </div>

      <section aria-label="Totals" className={styles.totals}>
        <Total label="Browser events" value={fmt(detail.browser)} note="Seen on the storefront and relayed" />
        <Total
          label="Reached Meta via server"
          value={sharePct(detail.sent, detail.browser)}
          note={`${fmt(detail.sent)} of ${fmt(detail.browser)} events`}
        />
        <Total
          label="Purchases"
          value={fmt(detail.purchases)}
          note={`${fmt(detail.purchases_sent)} sent to Meta with customer data`}
        />
        <Total
          label="Not sent yet"
          value={fmt(detail.not_sent)}
          note={notSentDetail(detail)}
          critical={detail.held > 0}
        />
      </section>

      <div className={styles.split}>
        <EventsByType detail={detail} query={query} />
        <section id="connection" className={`${styles.card} ${styles.side}`} aria-labelledby="connection-h">
          <div className={styles.cardHead}>
            <h2 id="connection-h" className={styles.cardTitle}>
              Pixel and Conversions API
            </h2>
            <ConnectionBadge market={market} />
          </div>
          {editing ? (
            <PixelForm market={market} onDone={() => setEditing(false)} />
          ) : (
            <ConnectionPanel market={market} onEdit={startEdit} stateFetcher={stateFetcher} />
          )}
        </section>
      </div>

      <EventsChart detail={detail} />
      <EventsTable events={events} detail={detail} query={query} />
    </>
  );
}

function Total({ label, value, note, critical }: { label: string; value: string; note: string; critical?: boolean }) {
  return (
    <div className={styles.card}>
      <s-text color="subdued">{label}</s-text>
      <b className={`${styles.big} ${critical ? styles.figureAttention : ""}`}>{value}</b>
      <span className={styles.note}>{note}</span>
    </div>
  );
}

function EventsByType({ detail, query }: { detail: MarketDetailRecord; query: Query }) {
  const rows = typeRows(detail);
  return (
    <section className={`${styles.card} ${styles.main}`} aria-labelledby="types-h">
      <div className={styles.cardHead}>
        <h2 id="types-h" className={styles.cardTitle}>
          Events by type
        </h2>
        <span className={styles.note}>Select a type to filter the table below</span>
      </div>
      {rows.length ? (
        <div className={styles.scrollX}>
          <div className={styles.typeTable}>
            <div className={`${styles.typeRow} ${styles.typeHead}`}>
              <span>Event</span>
              <span>Share of all events</span>
              <span className={styles.num}>Count</span>
              <span className={styles.num}>Share</span>
              <span className={styles.num}>Reached Meta</span>
            </div>
            {rows.map((row) => {
              const selected = query.event === row.event_name;
              return (
                <Link
                  key={row.event_name}
                  to={withQuery(query, { event: selected ? "" : row.event_name })}
                  className={styles.typeRow}
                  aria-current={selected ? "true" : undefined}
                  preventScrollReset
                >
                  <b>{row.event_name}</b>
                  <span className={styles.track}>
                    <span className={styles.fill} style={{ width: `${row.bar}%` }} />
                  </span>
                  <span className={styles.num}>{fmt(row.count)}</span>
                  <span className={styles.num}>{row.share}</span>
                  <b className={`${styles.num} ${row.low ? styles.low : styles.good}`}>{row.reached}</b>
                </Link>
              );
            })}
            <div className={`${styles.typeRow} ${styles.typeTotal}`}>
              <span>All events</span>
              <span />
              <span className={styles.num}>{fmt(detail.browser)}</span>
              <span className={styles.num}>100%</span>
              <span className={styles.num}>{sharePct(detail.sent, detail.browser)}</span>
            </div>
          </div>
        </div>
      ) : (
        <s-text color="subdued">No events in this range.</s-text>
      )}
    </section>
  );
}

function ConnectionPanel({
  market,
  onEdit,
  stateFetcher,
}: {
  market: MarketRecord;
  onEdit: () => void;
  stateFetcher: ReturnType<typeof useFetcher<ActionResult>>;
}) {
  const pixel = market.pixel!;
  const recheck = useFetcher<ActionResult>();
  const [confirmRemove, setConfirmRemove] = useState(false);
  const last = lastCheckLabel(pixel);
  const busy = stateFetcher.state !== "idle";
  const recheckError = recheck.data?.intent === "recheck" && !recheck.data.check.ok ? recheck.data.check.error : null;

  return (
    <>
      <dl className={styles.facts}>
        <dt>Pixel ID</dt>
        <dd className={styles.mono}>{pixel.pixel_id}</dd>
        <dt>Token</dt>
        <dd>
          {pixel.has_token ? (
            <>
              Saved{pixel.token_hint ? <> · ends in <span className={styles.mono}>…{pixel.token_hint}</span></> : null}
            </>
          ) : (
            "None saved"
          )}
        </dd>
        <dt>Check with Meta</dt>
        <dd className={last.ok === false ? styles.low : last.ok ? styles.good : undefined}>{last.text}</dd>
        <dt>Test event code</dt>
        <dd>{pixel.test_event_code || <s-text color="subdued">None</s-text>}</dd>
      </dl>
      {recheckError && !last.text.includes(recheckError) ? <s-text tone="critical">{recheckError}</s-text> : null}
      <div className={styles.acts}>
        <s-button variant="primary" onClick={onEdit}>
          Edit pixel and token
        </s-button>
        <s-button
          loading={recheck.state !== "idle"}
          disabled={!pixel.has_token}
          onClick={() => recheck.submit({ intent: "recheck" }, { method: "post" })}
        >
          Check with Meta
        </s-button>
      </div>
      <div className={styles.divider}>
        <div className={styles.toggleRow}>
          <div>
            <b>{pixel.active ? "Pixel is active" : "Pixel is deactivated"}</b>
            <div className={styles.note}>
              {pixel.active
                ? "Deactivate to stop browser and server events for this Market. The pixel and token stay saved."
                : "Turn it back on to send browser and server events again."}
            </div>
          </div>
          <s-button
            tone={pixel.active ? "critical" : undefined}
            variant={pixel.active ? "secondary" : "primary"}
            loading={busy}
            onClick={() => stateFetcher.submit({ intent: pixel.active ? "deactivate" : "reactivate" }, { method: "post" })}
          >
            {pixel.active ? "Deactivate" : "Reactivate"}
          </s-button>
        </div>
        {confirmRemove ? (
          <s-stack gap="small-200">
            <s-text>
              Remove the pixel ID and token for {market.name}? No events will be sent for this Market until you
              connect a pixel again.
            </s-text>
            <div className={styles.acts}>
              <s-button
                tone="critical"
                variant="primary"
                loading={busy}
                onClick={() => stateFetcher.submit({ intent: "remove" }, { method: "post" })}
              >
                Remove pixel
              </s-button>
              <s-button variant="tertiary" onClick={() => setConfirmRemove(false)}>
                Cancel
              </s-button>
            </div>
          </s-stack>
        ) : (
          <div>
            <s-button variant="tertiary" tone="critical" onClick={() => setConfirmRemove(true)}>
              Remove pixel
            </s-button>
          </div>
        )}
      </div>
    </>
  );
}

const value = (event: Event) => (event.currentTarget as HTMLInputElement).value;

function CheckResult({ check }: { check: PixelCheckRecord | null }) {
  if (!check) return null;
  return check.ok ? (
    <s-banner tone="success" heading="Meta accepted this pixel and token">
      The token can send events to this pixel.
    </s-banner>
  ) : (
    <s-banner tone="critical" heading="Check with Meta failed">
      {check.error}
    </s-banner>
  );
}

/** Edit pixel and token: Check with Meta must pass for exactly these values before
 * Save (the backend checks again on save). A blank token keeps the saved one. */
function PixelForm({ market, onDone }: { market: MarketRecord; onDone: () => void }) {
  const checkFetcher = useFetcher<ActionResult>();
  const saveFetcher = useFetcher<ActionResult>();
  const [pixelId, setPixelId] = useState(market.pixel?.pixel_id ?? "");
  const [token, setToken] = useState("");
  const [testEventCode, setTestEventCode] = useState(market.pixel?.test_event_code ?? "");

  const saveResult = saveFetcher.data;
  useEffect(() => {
    if (saveFetcher.state === "idle" && saveResult?.intent === "save" && saveResult.ok) onDone();
  }, [saveFetcher.state, saveResult, onDone]);

  const checkResult = checkFetcher.data?.intent === "check" ? checkFetcher.data : null;
  const current = checkResult?.checkedFor === checkKey(pixelId, token) ? checkResult.check : null;
  const passed = Boolean(current?.ok);
  const needsToken = tokenRequired(market);
  const busy = saveFetcher.state !== "idle";
  const saveError = saveResult?.intent === "save" && !saveResult.ok ? saveResult.error : null;
  const submit = (fetcher: typeof checkFetcher, intent: string) =>
    fetcher.submit({ intent, pixelId, token, testEventCode }, { method: "post" });

  return (
    <s-stack gap="base">
      <s-text-field
        label="Meta pixel ID"
        value={pixelId}
        required
        error={pixelId && !isValidPixelId(pixelId) ? PIXEL_ID_HINT : undefined}
        onInput={(e) => setPixelId(value(e))}
        onChange={(e) => setPixelId(value(e))}
      />
      <s-password-field
        label="Conversions API access token"
        value={token}
        required={needsToken}
        placeholder={needsToken ? "Paste the whole token" : "Paste a new token, or leave blank to keep the saved one"}
        error={tokenWarning(token) ?? undefined}
        onInput={(e) => setToken(value(e))}
        onChange={(e) => setToken(value(e))}
      />
      <s-text-field
        label="Test event code"
        value={testEventCode}
        placeholder="TEST12345"
        details="Optional. Only while you test in Events Manager; clear it for real traffic."
        onInput={(e) => setTestEventCode(value(e))}
        onChange={(e) => setTestEventCode(value(e))}
      />
      <CheckResult check={current} />
      {saveError ? (
        <s-banner tone="critical" heading="Not saved">
          {saveError}
        </s-banner>
      ) : null}
      <div className={styles.acts}>
        <s-button
          disabled={!canCheckWithMeta(market, { pixelId, token }) || busy}
          loading={checkFetcher.state !== "idle"}
          onClick={() => submit(checkFetcher, "check")}
        >
          Check with Meta
        </s-button>
        <s-button variant="primary" disabled={!passed || busy} loading={busy} onClick={() => submit(saveFetcher, "save")}>
          Save
        </s-button>
        <s-button variant="tertiary" disabled={busy} onClick={onDone}>
          Cancel
        </s-button>
      </div>
    </s-stack>
  );
}

function EventsChart({ detail }: { detail: MarketDetailRecord }) {
  const bars = chartBars(detail.series);
  const hourly = detail.range === "24h";
  const unit = hourly ? "hour" : "day";
  return (
    <section className={styles.card} aria-labelledby="chart-h">
      <div className={styles.cardHead}>
        <h2 id="chart-h" className={styles.cardTitle}>
          Events per {unit}
        </h2>
        <div className={styles.legend}>
          <span>
            <i className={styles.keySent} /> Reached Meta
          </span>
          <span>
            <i className={styles.keyHeld} /> Held
          </span>
          <span>
            <i className={styles.keyOther} /> Not sent
          </span>
        </div>
      </div>
      <div
        role="img"
        aria-label={`Events per ${unit}: ${fmt(detail.sent)} of ${fmt(detail.browser)} reached Meta`}
        className={styles.chart}
      >
        {bars.map((bar, i) => (
          <div key={i} className={styles.chartCol} title={`${bar.total} events`}>
            <div className={styles.barOther} style={{ height: `${bar.notSent}%` }} />
            <div className={styles.barHeld} style={{ height: `${bar.held}%` }} />
            <div className={styles.barSent} style={{ height: `${bar.sent}%` }} />
          </div>
        ))}
      </div>
      <div className={styles.axis}>
        {chartAxis(detail.range).map((label) => (
          <span key={label}>{label}</span>
        ))}
      </div>
    </section>
  );
}

const STATUS_TONE: Record<string, "success" | "critical" | "info" | "warning" | "neutral"> = {
  sent: "success",
  held: "warning",
  waiting: "info",
  rejected: "critical",
  failed: "critical",
  skipped: "neutral",
};

function EventsTable({ events, detail, query }: { events: EventPageRecord; detail: MarketDetailRecord; query: Query }) {
  const known = detail.types.map((t) => t.event_name);
  const names = [...known, ...Object.keys(events.event_counts).filter((n) => !known.includes(n)).sort()];
  const allCount = Object.values(events.event_counts).reduce((a, b) => a + b, 0);
  const statusAll = Object.values(events.status_counts).reduce((a, b) => a + b, 0);
  const lastPage = Math.max(1, Math.ceil(events.total / events.page_size));
  const filtered = Boolean(query.event || query.status || query.q);

  return (
    <section className={`${styles.card} ${styles.flush}`} aria-labelledby="table-h">
      <div className={styles.tableTop}>
        <div className={styles.cardHead}>
          <h2 id="table-h" className={styles.cardTitle}>
            Events
          </h2>
          <EventSearch query={query} />
        </div>
        <div role="group" aria-label="Filter by event" className={styles.chips}>
          <Chip to={withQuery(query, { event: "" })} pressed={!query.event} label="All events" count={allCount} />
          {names.map((name) => (
            <Chip
              key={name}
              to={withQuery(query, { event: name })}
              pressed={query.event === name}
              label={name}
              count={events.event_counts[name] ?? 0}
            />
          ))}
        </div>
        <div role="group" aria-label="Filter by status" className={styles.chips}>
          <span className={styles.note}>Status</span>
          <Chip to={withQuery(query, { status: "" })} pressed={!query.status} label="All" count={statusAll} />
          {statusChips(events.status_counts, query.status).map((chip) => (
            <Chip
              key={chip.key}
              to={withQuery(query, { status: chip.key })}
              pressed={query.status === chip.key}
              label={chip.label}
              count={chip.count}
            />
          ))}
        </div>
      </div>
      {events.rows.length ? (
        <s-table>
          <s-table-header-row>
            <s-table-header>Time</s-table-header>
            <s-table-header>Event</s-table-header>
            <s-table-header>Event ID</s-table-header>
            <s-table-header>Sent as</s-table-header>
            <s-table-header>Status</s-table-header>
            <s-table-header>Meta's answer</s-table-header>
          </s-table-header-row>
          <s-table-body>
            {events.rows.map((e) => (
              <s-table-row key={`${e.event_id}-${e.created_at}`}>
                <s-table-cell>{formatUtc(e.created_at)}</s-table-cell>
                <s-table-cell>{e.event_name}</s-table-cell>
                <s-table-cell>
                  <span className={styles.mono}>{e.event_id}</span>
                </s-table-cell>
                <s-table-cell>{e.sent_as}</s-table-cell>
                <s-table-cell>
                  <s-badge tone={STATUS_TONE[e.status] ?? "neutral"}>{statusLabel(e.status)}</s-badge>
                </s-table-cell>
                <s-table-cell>{e.detail ?? ""}</s-table-cell>
              </s-table-row>
            ))}
          </s-table-body>
        </s-table>
      ) : filtered ? (
        <div className={styles.emptyState}>No events match these filters.</div>
      ) : (
        <div className={styles.emptyState}>
          <b>No events yet</b>
          <p>
            Visit your store on this Market's domain and allow cookies. To watch the events arrive in Meta, add a test
            event code from Events Manager → Test events with Edit pixel and token, then clear it when you're done.
          </p>
        </div>
      )}
      <div className={`${styles.tableFoot} ${styles.between}`}>
        <s-text color="subdued">{pageLabel({ ...events, rows: events.rows.length })}</s-text>
        <div className={styles.acts}>
          <PageLink to={withQuery(query, { page: events.page - 1 })} disabled={events.page <= 1} label="Previous" />
          <PageLink to={withQuery(query, { page: events.page + 1 })} disabled={events.page >= lastPage} label="Next" />
        </div>
      </div>
    </section>
  );
}

const SEARCH_DELAY_MS = 350;

/** Searches as the merchant types. Enter in s-search-field doesn't submit a
 * surrounding form, so the URL is updated directly after a short pause. */
function EventSearch({ query }: { query: Query }) {
  const navigate = useNavigate();
  const [term, setTerm] = useState(query.q);
  useEffect(() => setTerm(query.q), [query.q]);
  useEffect(() => {
    if (term.trim() === query.q) return;
    const timer = setTimeout(
      () => navigate(withQuery(query, { q: term.trim() }), { replace: true, preventScrollReset: true }),
      SEARCH_DELAY_MS,
    );
    return () => clearTimeout(timer);
  }, [term, query, navigate]);

  return (
    <div className={styles.search}>
      <s-search-field
        label="Search"
        labelAccessibilityVisibility="exclusive"
        value={term}
        placeholder="Event ID or #order number"
        onInput={(e) => setTerm(value(e))}
        onChange={(e) => setTerm(value(e))}
      />
    </div>
  );
}

function Chip({ to, pressed, label, count }: { to: string; pressed: boolean; label: string; count: number }) {
  return (
    <Link to={to} className={styles.chip} aria-current={pressed ? "true" : undefined} preventScrollReset>
      {label} <span className={styles.chipCount}>{fmt(count)}</span>
    </Link>
  );
}

function PageLink({ to, disabled, label }: { to: string; disabled: boolean; label: string }) {
  if (disabled) {
    return (
      <span className={styles.pageLink} aria-disabled="true">
        {label}
      </span>
    );
  }
  return (
    <Link to={to} className={styles.pageLink} preventScrollReset>
      {label}
    </Link>
  );
}

/** Connect mode: pixel ID, a token the merchant always pastes, Check with Meta,
 * then Activate (which saves the pair, so the Market starts sending). */
function ConnectMode({ market, fetcher }: { market: MarketRecord; fetcher: ReturnType<typeof useFetcher<ActionResult>> }) {
  const checkFetcher = useFetcher<ActionResult>();
  const [pixelId, setPixelId] = useState("");
  const [token, setToken] = useState("");
  const checkResult = checkFetcher.data?.intent === "check" ? checkFetcher.data : null;
  const current = checkResult?.checkedFor === checkKey(pixelId, token) ? checkResult.check : null;
  const passed = Boolean(current?.ok);
  const busy = fetcher.state !== "idle";
  const saveError = fetcher.data?.intent === "save" && !fetcher.data.ok ? fetcher.data.error : null;
  const pixelBad = pixelId.length > 0 && !isValidPixelId(pixelId);
  const warning = tokenWarning(token);
  const regions = regionsLabel(market.regions) || market.name;

  return (
    <>
      <MarketHeader market={market} />
      <div className={styles.split}>
        <section className={`${styles.card} ${styles.main}`} aria-labelledby="connect-h">
          <div>
            <h2 id="connect-h" className={styles.cardTitle}>
              Connect a Meta pixel
            </h2>
            <s-text color="subdued">
              Shoppers in this Market get their own pixel. Until it's connected, no events are sent to Meta for them.
            </s-text>
          </div>
          <div className={styles.stepRow}>
            <span className={styles.stepNo} aria-hidden="true">
              1
            </span>
            <div className={styles.grow}>
              <s-text-field
                label="Pixel ID"
                value={pixelId}
                placeholder="e.g. 1290457710338842"
                required
                error={pixelBad ? PIXEL_ID_HINT : undefined}
                details={pixelBad ? undefined : "Events Manager → Data sources → your dataset → the ID under its name."}
                onInput={(e) => setPixelId(value(e))}
                onChange={(e) => setPixelId(value(e))}
              />
            </div>
          </div>
          <div className={styles.stepRow}>
            <span className={styles.stepNo} aria-hidden="true">
              2
            </span>
            <div className={styles.grow}>
              <s-password-field
                label="Conversions API token"
                value={token}
                required
                placeholder="Paste the whole token. It starts with EAA…"
                error={warning ?? undefined}
                details={warning ? undefined : "From this pixel's Settings → Conversions API → Generate access token."}
                onInput={(e) => setToken(value(e))}
                onChange={(e) => setToken(value(e))}
              />
            </div>
          </div>
          <div className={styles.stepRow}>
            <span className={styles.stepNo} aria-hidden="true">
              3
            </span>
            <div className={styles.grow}>
              <s-stack gap="small-200">
                <b>Check with Meta</b>
                <s-text color="subdued">
                  We ask Meta whether this token can send to this pixel. Nothing is recorded in Events Manager.
                </s-text>
                <CheckResult check={current} />
                <div>
                  <s-button
                    disabled={!canCheckWithMeta(market, { pixelId, token }) || busy}
                    loading={checkFetcher.state !== "idle"}
                    onClick={() => checkFetcher.submit({ intent: "check", pixelId, token }, { method: "post" })}
                  >
                    Check with Meta
                  </s-button>
                </div>
              </s-stack>
            </div>
          </div>
          {saveError ? (
            <s-banner tone="critical" heading="Not activated">
              {saveError}
            </s-banner>
          ) : null}
          <div className={`${styles.divider} ${styles.between}`}>
            <s-text color="subdued">
              {passed ? "Ready. Events start the moment you activate." : "Activate unlocks once Check with Meta passes."}
            </s-text>
            <div className={styles.acts}>
              <Link to="/app" className={styles.pageLink}>
                Cancel
              </Link>
              <s-button
                variant="primary"
                disabled={!passed || busy}
                loading={busy}
                onClick={() => fetcher.submit({ intent: "save", activate: "1", pixelId, token }, { method: "post" })}
              >
                Activate pixel
              </s-button>
            </div>
          </div>
        </section>
        <aside className={styles.side}>
          <section className={styles.card} aria-labelledby="where-h">
            <h2 id="where-h" className={styles.cardTitle}>
              Where to find these in Meta
            </h2>
            <ol className={styles.list}>
              <li>
                Open Events Manager → <b>Data sources</b> and pick the dataset for {regions}. Its ID is under the name.
              </li>
              <li>
                Open <b>Settings</b> → <b>Conversions API</b> → <b>Generate access token</b>. Copy the whole token: it's
                about 200 characters.
              </li>
              <li>
                Just connected a new dataset to the token? Meta can take a few minutes to allow it. If the check fails,
                wait and try again.
              </li>
            </ol>
          </section>
          <section className={styles.card} aria-labelledby="what-h">
            <h2 id="what-h" className={styles.cardTitle}>
              What activating does
            </h2>
            <ul className={styles.list}>
              <li>Shoppers in {regions} who allow cookies send browser events to this pixel.</li>
              <li>
                The same events also reach Meta from our server, matched by event ID so Meta counts each one once.
              </li>
              <li>You can deactivate the pixel later from this page without losing the ID or token.</li>
            </ul>
          </section>
        </aside>
      </div>
    </>
  );
}

// Shopify's embedded-app headers (CSP frame-ancestors) on this document too.
export const headers: HeadersFunction = (headersArgs) => boundary.headers(headersArgs);
