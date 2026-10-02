import { useEffect, useRef, useState } from "react";
import type { ActionFunctionArgs, LoaderFunctionArgs, ShouldRevalidateFunction } from "react-router";
import { Link, useFetcher, useLoaderData, useRouteLoaderData, useSearchParams } from "react-router";
import { authenticate } from "../shopify.server";
import {
  checkMarketPixel,
  listMarkets,
  removeMarketPixel,
  saveMarketPixel,
  updateSetup,
  type EventLogRecord,
  type MarketRecord,
  type PixelCheckRecord,
} from "../backend.server";
import { BackendRequestError } from "../backend-fetch.helpers.mjs";
import { withRequestContext } from "../request-context.server";
import { logError } from "../logger.server";
import {
  addedAgo,
  canCheckWithMeta,
  heldEventAlerts,
  isValidPixelId,
  lastEventLabel,
  marketLabels,
  marketTileState,
  normalizePixelId,
  PIXEL_ID_HINT,
  regionsLabel,
  serverShare,
  setupSteps,
  sparkBars,
  summarizeMarkets,
  tokenRequired,
} from "../markets.shared.mjs";
import styles from "../markets.module.css";

const EDITOR_ID = "pixel-editor";
const EVENT_LOG_ID = "event-log";
// The theme app embed's block (extensions/multi-pixel-embed/blocks/multi-pixel.liquid).
const EMBED_BLOCK = "multi-pixel";
const NUMBER = new Intl.NumberFormat("en-US");

export const loader = async ({ request }: LoaderFunctionArgs) => {
  const { session } = await authenticate.admin(request);
  return withRequestContext(request, session.shop, async () => {
    // Opening the app re-fetches the Markets (spec §5); a failed re-fetch still
    // shows the stored list with a warning.
    try {
      const { markets, summary, setup, sync_error } = await listMarkets(session.shop, { sync: true });
      return { markets, summary, setup, syncError: sync_error, loadFailed: false };
    } catch (error) {
      logError("markets_load_failed", error, { shop: session.shop });
      return {
        markets: [] as MarketRecord[],
        summary: { browser_24h: 0, server_24h: 0 },
        setup: { consent_confirmed: false, verified_in_meta: false },
        syncError: null,
        loadFailed: true,
      };
    }
  });
};

type ActionResult =
  | { intent: "check"; checkedFor: string; check: PixelCheckRecord }
  | { intent: "save" | "remove" | "setup"; ok: true }
  | { intent: "save" | "remove"; ok: false; error: string };

export const action = async ({ request }: ActionFunctionArgs): Promise<ActionResult> => {
  const { session } = await authenticate.admin(request);
  const form = await request.formData();
  const intent = String(form.get("intent"));
  const marketId = Number(form.get("marketId"));
  const input = {
    pixel_id: normalizePixelId(form.get("pixelId")),
    token: String(form.get("token") ?? "").trim(),
    test_event_code: String(form.get("testEventCode") ?? "").trim(),
  };
  return withRequestContext(request, session.shop, async () => {
    if (intent === "check") {
      const check = await checkMarketPixel(session.shop, marketId, input);
      return { intent, checkedFor: checkKey(input.pixel_id, input.token), check };
    }
    if (intent === "setup") {
      const step = String(form.get("step"));
      await updateSetup(session.shop, step === "consent" ? { consent_confirmed: true } : { verified_in_meta: true });
      return { intent, ok: true };
    }
    const save = intent === "save";
    try {
      if (save) await saveMarketPixel(session.shop, marketId, input);
      else await removeMarketPixel(session.shop, marketId);
      return { intent: save ? "save" : "remove", ok: true };
    } catch (error) {
      if (error instanceof BackendRequestError && (error.status === 422 || error.status === 404)) {
        return { intent: save ? "save" : "remove", ok: false, error: error.detail };
      }
      throw error;
    }
  });
};

// A check only answers the editor; it must not re-fetch the Markets.
export const shouldRevalidate: ShouldRevalidateFunction = ({ formData, defaultShouldRevalidate }) =>
  formData?.get("intent") === "check" ? false : defaultShouldRevalidate;

function checkKey(pixelId: string, token: string) {
  return `${normalizePixelId(pixelId)}\n${token.trim()}`;
}

type ShopifyGlobal = {
  app?: { extensions?: () => Promise<{ handle: string; type: string; status: string; activations?: { handle?: string; status: string }[] }[]> };
};

/** Whether the theme app embed is on in the published theme, read with App
 * Bridge's app.extensions() (spec §4). null while unknown. */
function useEmbedActive(): boolean | null {
  const [active, setActive] = useState<boolean | null>(null);
  useEffect(() => {
    const extensions = (globalThis as unknown as { shopify?: ShopifyGlobal }).shopify?.app?.extensions;
    if (!extensions) return;
    extensions()
      .then((list) => {
        const themeExtensions = list.filter((e) => e.type === "theme_app_extension");
        setActive(
          themeExtensions.some(
            (e) => e.status === "active" || (e.activations ?? []).some((a) => a.status === "active"),
          ),
        );
      })
      .catch(() => setActive(false));
  }, []);
  return active;
}

export default function Markets() {
  const { markets, summary: totals, setup, syncError, loadFailed } = useLoaderData<typeof loader>();
  const appData = useRouteLoaderData("routes/app") as { apiKey?: string; plan?: { name: string } | null; billingEnabled?: boolean } | undefined;
  const modalRef = useRef<HTMLElementTagNameMap["s-modal"]>(null);
  // Each opening gets a fresh form, even when the same Market is opened again.
  const [editor, setEditor] = useState({ marketId: null as number | null, opened: 0 });
  const editing = markets.find((m) => m.shopify_market_id === editor.marketId) ?? null;
  const openEditor = (marketId: number) => setEditor((e) => ({ marketId, opened: e.opened + 1 }));
  const [logMarket, setLogMarket] = useState<number | null>(null);
  // The held-events banner on the other pages links here with ?fix=<Market ID>.
  const [searchParams, setSearchParams] = useSearchParams();
  const fixMarket = Number(searchParams.get("fix")) || null;
  useEffect(() => {
    if (!fixMarket || !markets.some((m) => m.shopify_market_id === fixMarket)) return;
    openEditor(fixMarket);
    modalRef.current?.showOverlay();
    setSearchParams((params) => {
      params.delete("fix");
      return params;
    }, { replace: true });
  }, [fixMarket, markets, setSearchParams]);
  const alerts = heldEventAlerts(markets);
  const summary = summarizeMarkets(markets);
  const embedActive = useEmbedActive();
  const steps = setupSteps({ embedActive, markets, setup });
  const setupFetcher = useFetcher();
  const confirm = (step: string) => setupFetcher.submit({ intent: "setup", step }, { method: "post" });
  const activateEmbed = () => {
    const url = `shopify://admin/themes/current/editor?context=apps&activateAppId=${appData?.apiKey ?? ""}/${EMBED_BLOCK}`;
    window.open(url, "_top");
  };

  return (
    <s-page heading="Markets">
      <s-button slot="secondary-actions" commandFor={EVENT_LOG_ID} command="--show" onClick={() => setLogMarket(null)}>
        Event log
      </s-button>
      <s-stack gap="base">
        {appData?.billingEnabled ? (
          <s-stack direction="inline" gap="small-200" alignItems="center">
            <s-badge tone="info">{appData.plan ? `${appData.plan.name} plan` : "No plan"}</s-badge>
          </s-stack>
        ) : null}

        {loadFailed ? (
          <s-banner tone="critical" heading="Markets couldn't be loaded">
            The app's backend didn't answer. Reload the page in a moment.
          </s-banner>
        ) : null}
        {syncError ? (
          <s-banner tone="warning" heading="Couldn't refresh your Markets from Shopify">
            Showing the Markets as they were last fetched. Reload the page to try again.
          </s-banner>
        ) : null}

        {alerts.map((alert) => (
          <s-banner key={alert.marketId} tone="critical" heading={alert.heading}>
            {alert.text}
            <s-button
              slot="secondary-actions"
              commandFor={EDITOR_ID}
              command="--show"
              onClick={() => openEditor(alert.marketId)}
            >
              Update token
            </s-button>
          </s-banner>
        ))}

        {steps.some((s) => !s.done) ? (
          <div className={styles.strip}>
            <b>Setup</b>
            {steps.map((step) => (
              <span key={step.key} className={`${styles.pill} ${step.done ? "" : styles.todo}`}>
                {step.done ? "✓" : "○"} {step.label}
              </span>
            ))}
            <span className={styles.grow} />
            {!steps[0].done ? (
              <s-button variant="primary" onClick={activateEmbed}>
                Turn on the app embed
              </s-button>
            ) : null}
            {!steps[2].done ? (
              <s-button onClick={() => confirm("consent")}>My store asks for cookie consent</s-button>
            ) : null}
            {!steps[3].done ? (
              <s-button onClick={() => confirm("verified")}>I checked Events Manager</s-button>
            ) : null}
            <Link to="/app/help">Help</Link>
          </div>
        ) : null}

        <div className={styles.summary}>
          <div>
            <s-text color="subdued">Markets sending</s-text>
            <b className={styles.figure}>
              {summary.sending} of {summary.total}
            </b>
          </div>
          <div>
            <s-text color="subdued">Need attention</s-text>
            <b className={`${styles.figure} ${summary.attention ? styles.figureAttention : ""}`}>{summary.attention}</b>
          </div>
          <div>
            <s-text color="subdued">Browser events, 24 h</s-text>
            <b className={styles.figure}>{NUMBER.format(totals.browser_24h)}</b>
          </div>
          <div>
            <s-text color="subdued">Reached Meta via server</s-text>
            <b className={styles.figure}>{serverShare(totals)}</b>
          </div>
        </div>

        <div className={styles.tiles}>
          {markets.map((market) => (
            <MarketTile key={market.shopify_market_id} market={market} onEdit={openEditor} onEvents={setLogMarket} />
          ))}
        </div>

        <s-text color="subdued">
          Counts are for the last 24 hours. Server events are matched to browser events by event ID, so Meta counts
          each one once.
        </s-text>
      </s-stack>

      {/* One stable modal; only the form inside is replaced per opening. */}
      <s-modal
        id={EDITOR_ID}
        ref={modalRef}
        heading={editing ? `${editing.pixel ? "Edit" : "Add"} pixel for ${editing.name}` : "Pixel"}
      >
        {editing ? (
          <PixelEditor
            key={editor.opened}
            market={editing}
            onSaved={() => modalRef.current?.hideOverlay()}
          />
        ) : null}
      </s-modal>

      <EventLog marketId={logMarket} markets={markets} />
    </s-page>
  );
}

function Spark({ series, tone }: { series: number[]; tone: "ok" | "crit" }) {
  const bars = sparkBars(series, { width: 240, height: 36 });
  const color = tone === "crit" ? "#d72c0d" : "#29845a";
  return (
    <svg className={styles.spark} viewBox="0 0 240 36" preserveAspectRatio="none" aria-label="Events per hour, last 24 hours">
      {bars.map((bar, i) => (
        <rect
          key={i}
          x={bar.x}
          y={36 - bar.height}
          width={bar.width}
          height={bar.height}
          rx={1}
          fill={color}
          opacity={i === bars.length - 1 ? 1 : 0.55}
        />
      ))}
    </svg>
  );
}

function MarketTile({
  market,
  onEdit,
  onEvents,
}: {
  market: MarketRecord;
  onEdit: (id: number) => void;
  onEvents: (id: number) => void;
}) {
  const state = marketTileState(market);
  const labels = marketLabels(market);
  const regions = regionsLabel(market.regions);
  const open = () => onEdit(market.shopify_market_id);

  const heading = (
    <div className={styles.grow}>
      <s-stack direction="inline" gap="small-200" alignItems="center">
        <s-heading>{market.name}</s-heading>
        {labels.map((label) => (
          <s-badge key={label}>{label}</s-badge>
        ))}
      </s-stack>
      {regions ? <s-text color="subdued">{regions}</s-text> : null}
    </div>
  );

  if (!market.pixel) {
    const isNew = state === "new";
    return (
      <div className={`${styles.tile} ${styles.empty}`}>
        <div className={styles.row1}>
          {heading}
          <s-badge tone={isNew ? "warning" : "neutral"}>{isNew ? "New · no pixel" : "No pixel"}</s-badge>
        </div>
        <s-paragraph color="subdued">
          {isNew ? `This Market was ${addedAgo(market.first_seen_at)}. ` : ""}
          No events are sent for shoppers in this Market.
        </s-paragraph>
        <div className={styles.acts}>
          <s-button variant={isNew ? "primary" : "secondary"} commandFor={EDITOR_ID} command="--show" onClick={open}>
            Add pixel
          </s-button>
        </div>
      </div>
    );
  }

  const problem = state === "token_problem";
  const { stats } = market;
  return (
    <div className={`${styles.tile} ${problem ? styles.problem : styles.sending}`}>
      <div className={styles.row1}>
        {heading}
        <s-badge tone={problem ? "critical" : "success"}>{problem ? "Token problem" : "Sending"}</s-badge>
      </div>
      <div>
        <s-text color="subdued">Pixel</s-text> {market.pixel.pixel_name ? <s-text>{market.pixel.pixel_name}</s-text> : null}{" "}
        <span className={styles.mono}>{market.pixel.pixel_id}</span>
      </div>
      {problem ? (
        <s-paragraph tone="critical">
          Meta rejected the Conversions API token{market.pixel.token_error ? ` (${market.pixel.token_error})` : ""}.
          Browser events still send; server events are on hold. Paste a new token.
        </s-paragraph>
      ) : null}
      <Spark series={stats.series} tone={problem ? "crit" : "ok"} />
      <div className={styles.counts}>
        <div>
          <b>{NUMBER.format(stats.browser)}</b>
          <span>Browser</span>
        </div>
        <div>
          <b>{NUMBER.format(stats.server)}</b>
          <span>Server</span>
        </div>
        <div>
          <b>{NUMBER.format(stats.purchases)}</b>
          <span>Purchases</span>
        </div>
      </div>
      <s-text color="subdued">{lastEventLabel(stats.last_event_at)}</s-text>
      <div className={styles.acts}>
        <s-button variant={problem ? "primary" : "secondary"} commandFor={EDITOR_ID} command="--show" onClick={open}>
          {problem ? "Update token" : "Edit pixel"}
        </s-button>
        <s-button
          variant="tertiary"
          commandFor={EVENT_LOG_ID}
          command="--show"
          onClick={() => onEvents(market.shopify_market_id)}
        >
          View events
        </s-button>
      </div>
    </div>
  );
}

const STATUS_TONE: Record<string, "success" | "critical" | "info" | "warning" | "neutral"> = {
  sent: "success",
  failed: "critical",
  rejected: "critical",
  paused: "warning",
  waiting: "info",
  received: "info",
  skipped: "neutral",
};

/** The event log (spec §4): all events, or one Market's. Kept for 30 days. */
function EventLog({ marketId, markets }: { marketId: number | null; markets: MarketRecord[] }) {
  const fetcher = useFetcher<{ events: EventLogRecord[] }>();
  const { load } = fetcher;
  const [opened, setOpened] = useState(0);
  useEffect(() => {
    if (opened) load(`/app/events${marketId ? `?market=${marketId}` : ""}`);
  }, [opened, marketId, load]);
  const name = (id: number) => markets.find((m) => m.shopify_market_id === id)?.name ?? (id ? String(id) : "—");
  const events = fetcher.data?.events ?? [];

  return (
    <s-modal
      id={EVENT_LOG_ID}
      size="large"
      heading={marketId ? `Events · ${name(marketId)}` : "Event log"}
      onShow={() => setOpened((n) => n + 1)}
    >
      <s-stack gap="base">
        <s-text color="subdued">
          Most recent first. Skipped events were not sent; rejected Relays were refused before reaching Meta.
        </s-text>
        {fetcher.state !== "idle" && !fetcher.data ? <s-spinner /> : null}
        {fetcher.data && !events.length ? <s-text color="subdued">No events in the last 30 days.</s-text> : null}
        {events.length ? (
          <s-table>
            <s-table-header-row>
              <s-table-header>Time</s-table-header>
              <s-table-header>Event</s-table-header>
              <s-table-header>Market</s-table-header>
              <s-table-header>Sent as</s-table-header>
              <s-table-header>Status</s-table-header>
              <s-table-header>Meta's answer</s-table-header>
            </s-table-header-row>
            <s-table-body>
              {events.map((e) => (
                <s-table-row key={`${e.event_id}-${e.created_at}`}>
                  <s-table-cell>{new Date(e.created_at).toLocaleString("en-GB")}</s-table-cell>
                  <s-table-cell>{e.event_name}</s-table-cell>
                  <s-table-cell>{name(e.shopify_market_id)}</s-table-cell>
                  <s-table-cell>{e.sent_as}</s-table-cell>
                  <s-table-cell>
                    <s-badge tone={STATUS_TONE[e.status] ?? "neutral"}>{e.status}</s-badge>
                  </s-table-cell>
                  <s-table-cell>{e.detail ?? ""}</s-table-cell>
                </s-table-row>
              ))}
            </s-table-body>
          </s-table>
        ) : null}
      </s-stack>
    </s-modal>
  );
}

/** The pixel editor: pixel ID + token both required, Check with Meta must pass
 * for exactly these values before Save (the backend checks again on save). */
function PixelEditor({ market, onSaved }: { market: MarketRecord; onSaved: () => void }) {
  const checkFetcher = useFetcher<ActionResult>();
  const saveFetcher = useFetcher<ActionResult>();
  const [pixelId, setPixelId] = useState(market.pixel?.pixel_id ?? "");
  const [token, setToken] = useState("");
  const [testEventCode, setTestEventCode] = useState(market.pixel?.test_event_code ?? "");

  const saveResult = saveFetcher.data;
  useEffect(() => {
    if (saveFetcher.state === "idle" && saveResult && "ok" in saveResult && saveResult.ok) {
      onSaved();
    }
  }, [saveFetcher.state, saveResult, onSaved]);

  const checkResult = checkFetcher.data?.intent === "check" ? checkFetcher.data : null;
  const passedFor = checkResult?.check.ok ? checkResult.checkedFor : null;
  const passed = passedFor === checkKey(pixelId, token);
  const showCheck = checkResult && checkResult.checkedFor === checkKey(pixelId, token) ? checkResult.check : null;
  const pixelError = pixelId && !isValidPixelId(pixelId) ? PIXEL_ID_HINT : undefined;
  const needsToken = tokenRequired(market);
  const busy = saveFetcher.state !== "idle";
  const saveError = saveResult && "ok" in saveResult && !saveResult.ok ? saveResult.error : null;

  const fields = { intent: "", marketId: String(market.shopify_market_id), pixelId, token, testEventCode };
  const submit = (fetcher: typeof checkFetcher, intent: string) =>
    fetcher.submit({ ...fields, intent }, { method: "post" });
  const value = (event: Event) => (event.currentTarget as HTMLInputElement).value;

  return (
    <s-stack gap="base">
      {regionsLabel(market.regions) || marketLabels(market).length ? (
        <s-text color="subdued">
          {[regionsLabel(market.regions), ...marketLabels(market).map((l) => `${l} Market`)].filter(Boolean).join(" · ")}
        </s-text>
      ) : null}
      {market.pixel?.token_state === "rejected" ? (
        <s-banner tone="critical" heading="Meta rejected the current token">
          Server events for this Market are on hold until you paste a new token.
        </s-banner>
      ) : null}
      <s-text-field
        label="Meta pixel ID"
        value={pixelId}
        placeholder="e.g. 1290457710338842"
        required
        error={pixelError}
        details="Events Manager → Data sources → your pixel → Dataset ID."
        onInput={(e) => setPixelId(value(e))}
        onChange={(e) => setPixelId(value(e))}
      />
      <s-password-field
        label="Conversions API access token"
        value={token}
        required={needsToken}
        placeholder={needsToken ? "Paste the token" : "Saved. Paste a new token to replace it"}
        details="Events Manager → your pixel → Settings → Conversions API → Generate access token. Every mapped Market sends browser and server events, so the token is required."
        onInput={(e) => setToken(value(e))}
        onChange={(e) => setToken(value(e))}
      />
      {/* Adding a pixel is just ID + token; testing in Events Manager comes after it's saved. */}
      {market.pixel ? (
        <s-text-field
          label="Test event code"
          value={testEventCode}
          placeholder="TEST12345"
          details="Optional. Only while you test in Events Manager; clear it for real traffic."
          onInput={(e) => setTestEventCode(value(e))}
          onChange={(e) => setTestEventCode(value(e))}
        />
      ) : null}
      {showCheck ? (
        showCheck.ok ? (
          <s-banner tone="success" heading="Meta accepted this pixel and token">
            The token can send events to this pixel.
          </s-banner>
        ) : (
          <s-banner tone="critical" heading="Check with Meta failed">
            {showCheck.error}
          </s-banner>
        )
      ) : null}
      {saveError ? (
        <s-banner tone="critical" heading="Not saved">
          {saveError}
        </s-banner>
      ) : null}
      <s-stack direction="inline" gap="small-200">
        {market.pixel ? (
          <s-button tone="critical" disabled={busy} onClick={() => submit(saveFetcher, "remove")}>
            Remove pixel
          </s-button>
        ) : null}
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
      </s-stack>
    </s-stack>
  );
}
