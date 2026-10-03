import { useEffect, useState } from "react";
import { RefreshButton } from "../components/refresh-button";
import type { HeadersFunction, ActionFunctionArgs, LoaderFunctionArgs } from "react-router";
import { boundary } from "@shopify/shopify-app-react-router/server";
import { Link, useFetcher, useLoaderData, useNavigate, useRouteLoaderData } from "react-router";
import { authenticate } from "../shopify.server";
import { listMarkets, updateSetup, type MarketRecord } from "../backend.server";
import { withRequestContext } from "../request-context.server";
import { logError } from "../logger.server";
import {
  addedAgo,
  heldEventAlerts,
  lastEventLabel,
  marketLabels,
  marketTileState,
  regionsLabel,
  serverShare,
  setupSteps,
  sparkBars,
  summarizeMarkets,
} from "../markets.shared.mjs";
import styles from "../markets.module.css";

// The theme app embed's block (extensions/multi-pixel-embed/blocks/multi-pixel.liquid).
const EMBED_BLOCK = "multi-pixel";
const NUMBER = new Intl.NumberFormat("en-US");

export const loader = async ({ request }: LoaderFunctionArgs) => {
  const { session } = await authenticate.admin(request);
  return withRequestContext(request, session.shop, async () => {
    const loadedAt = new Date().toISOString();
    // Opening the app re-fetches the Markets (spec §5); a failed re-fetch still
    // shows the stored list with a warning.
    try {
      const { markets, summary, setup, sync_error } = await listMarkets(session.shop, { sync: true });
      return { markets, summary, setup, syncError: sync_error, loadFailed: false, loadedAt };
    } catch (error) {
      logError("markets_load_failed", error, { shop: session.shop });
      return {
        markets: [] as MarketRecord[],
        summary: { browser_24h: 0, server_24h: 0 },
        setup: { consent_confirmed: false, verified_in_meta: false },
        syncError: null,
        loadFailed: true,
        loadedAt,
      };
    }
  });
};

export const action = async ({ request }: ActionFunctionArgs) => {
  const { session } = await authenticate.admin(request);
  const form = await request.formData();
  return withRequestContext(request, session.shop, async () => {
    const step = String(form.get("step"));
    await updateSetup(session.shop, step === "consent" ? { consent_confirmed: true } : { verified_in_meta: true });
    return { ok: true };
  });
};

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

/** The Markets overview (#15): one status tile per Market. Each Market's pixel,
 * figures and events are on its own page. */
export default function Markets() {
  const { markets, summary: totals, setup, syncError, loadFailed, loadedAt } = useLoaderData<typeof loader>();
  const appData = useRouteLoaderData("routes/app") as { apiKey?: string; plan?: { name: string } | null; billingEnabled?: boolean } | undefined;
  const navigate = useNavigate();
  const alerts = heldEventAlerts(markets);
  const summary = summarizeMarkets(markets);
  const embedActive = useEmbedActive();
  const steps = setupSteps({ embedActive, markets, setup });
  const setupFetcher = useFetcher();
  const confirm = (step: string) => setupFetcher.submit({ step }, { method: "post" });
  const activateEmbed = () => {
    const url = `shopify://admin/themes/current/editor?context=apps&activateAppId=${appData?.apiKey ?? ""}/${EMBED_BLOCK}`;
    window.open(url, "_top");
  };

  return (
    <s-page heading="Markets" inlineSize="large">
      <s-stack gap="base">
        <s-stack direction="inline" gap="small-200" alignItems="center" justifyContent="space-between">
          {appData?.billingEnabled ? (
            <s-badge tone="info">{appData.plan ? `${appData.plan.name} plan` : "No plan"}</s-badge>
          ) : (
            <span />
          )}
          <RefreshButton loadedAt={loadedAt} />
        </s-stack>

        {loadFailed ? (
          <s-banner tone="critical" heading="Markets couldn't be loaded">
            The app's backend didn't answer. Try Refresh in a moment.
          </s-banner>
        ) : null}
        {syncError ? (
          <s-banner tone="warning" heading="Couldn't refresh your Markets from Shopify">
            Showing the Markets as they were last fetched. Try Refresh in a moment.
          </s-banner>
        ) : null}

        {alerts.map((alert) => (
          <s-banner key={alert.marketId} tone="critical" heading={alert.heading}>
            {alert.text}
            <s-button slot="secondary-actions" onClick={() => navigate(`/app/markets/${alert.marketId}`)}>
              View {alert.name}
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
            <MarketTile
              key={market.shopify_market_id}
              market={market}
              onOpen={() => navigate(`/app/markets/${market.shopify_market_id}`)}
            />
          ))}
        </div>

        <s-text color="subdued">
          Counts are for the last 24 hours. Server events are matched to browser events by event ID, so Meta counts
          each one once.
        </s-text>
      </s-stack>
    </s-page>
  );
}

function Spark({ series, tone }: { series: number[]; tone: "ok" | "crit" | "off" }) {
  const bars = sparkBars(series, { width: 240, height: 36 });
  const color = tone === "crit" ? "#d72c0d" : tone === "off" ? "#8a8a8a" : "#29845a";
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

const TILE_BADGE = {
  sending: { tone: "success", label: "Sending", className: styles.sending },
  token_problem: { tone: "critical", label: "Token problem", className: styles.problem },
  deactivated: { tone: "neutral", label: "Deactivated", className: styles.off },
} as const;

function MarketTile({ market, onOpen }: { market: MarketRecord; onOpen: () => void }) {
  const state = marketTileState(market);
  const labels = marketLabels(market);
  const regions = regionsLabel(market.regions);

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
          <s-badge tone={isNew ? "warning" : "neutral"}>{isNew ? "New · not configured" : "Not configured"}</s-badge>
        </div>
        <s-paragraph color="subdued">
          {isNew ? `This Market was ${addedAgo(market.first_seen_at)}. ` : ""}
          No pixel yet, so no events are sent to Meta for shoppers in this Market.
        </s-paragraph>
        <div className={`${styles.acts} ${styles.end}`}>
          <s-button variant="primary" accessibilityLabel={`Configure ${market.name}`} onClick={onOpen}>
            Configure
          </s-button>
        </div>
      </div>
    );
  }

  const badge = TILE_BADGE[state as keyof typeof TILE_BADGE] ?? TILE_BADGE.sending;
  const { stats } = market;
  return (
    <div className={`${styles.tile} ${badge.className}`}>
      <div className={styles.row1}>
        {heading}
        <s-badge tone={badge.tone}>{badge.label}</s-badge>
      </div>
      <div>
        <s-text color="subdued">Pixel</s-text> <span className={styles.monoDark}>{market.pixel.pixel_id}</span>
      </div>
      <Spark series={stats.series} tone={state === "token_problem" ? "crit" : state === "deactivated" ? "off" : "ok"} />
      <div className={styles.counts}>
        <div>
          <b>{NUMBER.format(stats.browser)}</b>
          <span>Browser</span>
        </div>
        <div>
          <b>{serverShare({ browser_24h: stats.browser, server_24h: stats.server })}</b>
          <span>Reached Meta</span>
        </div>
        <div>
          <b>{NUMBER.format(stats.purchases)}</b>
          <span>Purchases</span>
        </div>
      </div>
      <div className={`${styles.acts} ${styles.between}`}>
        <s-text color="subdued">{lastEventLabel(stats.last_event_at)}</s-text>
        <s-button accessibilityLabel={`View ${market.name}`} onClick={onOpen}>
          View
        </s-button>
      </div>
    </div>
  );
}

// Shopify's embedded-app headers (CSP frame-ancestors) on this document too.
export const headers: HeadersFunction = (headersArgs) => boundary.headers(headersArgs);
