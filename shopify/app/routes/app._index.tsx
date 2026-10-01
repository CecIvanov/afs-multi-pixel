import { useEffect, useRef, useState } from "react";
import type { ActionFunctionArgs, LoaderFunctionArgs, ShouldRevalidateFunction } from "react-router";
import { useFetcher, useLoaderData } from "react-router";
import { authenticate } from "../shopify.server";
import {
  checkMarketPixel,
  listMarkets,
  removeMarketPixel,
  saveMarketPixel,
  type MarketRecord,
  type PixelCheckRecord,
} from "../backend.server";
import { BackendRequestError } from "../backend-fetch.helpers.mjs";
import { withRequestContext } from "../request-context.server";
import { logError } from "../logger.server";
import {
  addedAgo,
  canCheckWithMeta,
  isValidPixelId,
  marketLabels,
  marketTileState,
  normalizePixelId,
  PIXEL_ID_HINT,
  regionsLabel,
  summarizeMarkets,
  tokenRequired,
} from "../markets.shared.mjs";
import styles from "../markets.module.css";

const EDITOR_ID = "pixel-editor";
// The plan badge is a placeholder until the subscription check lands (#10).
const PLAN_LABEL = "Plan";

export const loader = async ({ request }: LoaderFunctionArgs) => {
  const { session } = await authenticate.admin(request);
  return withRequestContext(request, session.shop, async () => {
    // Opening the app re-fetches the Markets (spec §5); a failed re-fetch still
    // shows the stored list with a warning.
    try {
      const { markets, sync_error } = await listMarkets(session.shop, { sync: true });
      return { markets, syncError: sync_error, loadFailed: false };
    } catch (error) {
      logError("markets_load_failed", error, { shop: session.shop });
      return { markets: [] as MarketRecord[], syncError: null, loadFailed: true };
    }
  });
};

type ActionResult =
  | { intent: "check"; checkedFor: string; check: PixelCheckRecord }
  | { intent: "save" | "remove"; ok: true }
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

export default function Markets() {
  const { markets, syncError, loadFailed } = useLoaderData<typeof loader>();
  const modalRef = useRef<HTMLElementTagNameMap["s-modal"]>(null);
  // Each opening gets a fresh form, even when the same Market is opened again.
  const [editor, setEditor] = useState({ marketId: null as number | null, opened: 0 });
  const editing = markets.find((m) => m.shopify_market_id === editor.marketId) ?? null;
  const openEditor = (marketId: number) => setEditor((e) => ({ marketId, opened: e.opened + 1 }));
  const summary = summarizeMarkets(markets);

  return (
    <s-page heading="Markets">
      <s-stack gap="base">
        <s-stack direction="inline" gap="small-200" alignItems="center">
          <s-badge tone="info">{PLAN_LABEL}</s-badge>
        </s-stack>

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
            <b className={styles.figure}>—</b>
          </div>
          <div>
            <s-text color="subdued">Reached Meta via server</s-text>
            <b className={styles.figure}>—</b>
          </div>
        </div>

        <div className={styles.tiles}>
          {markets.map((market) => (
            <MarketTile key={market.shopify_market_id} market={market} onEdit={openEditor} />
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
    </s-page>
  );
}

function MarketTile({ market, onEdit }: { market: MarketRecord; onEdit: (id: number) => void }) {
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
  return (
    <div className={`${styles.tile} ${problem ? styles.problem : styles.sending}`}>
      <div className={styles.row1}>
        {heading}
        <s-badge tone={problem ? "critical" : "success"}>{problem ? "Token problem" : "Sending"}</s-badge>
      </div>
      <div>
        <s-text color="subdued">Pixel</s-text> <s-text>{market.pixel.pixel_name ?? "Unnamed pixel"}</s-text>{" "}
        <span className={styles.mono}>{market.pixel.pixel_id}</span>
      </div>
      {problem ? (
        <s-paragraph tone="critical">
          Meta rejected the Conversions API token. Browser events still send; server events are on hold. Paste a new
          token.
        </s-paragraph>
      ) : null}
      <div className={styles.counts}>
        <div>
          <b>—</b>
          <span>Browser</span>
        </div>
        <div>
          <b>—</b>
          <span>Server</span>
        </div>
        <div>
          <b>—</b>
          <span>Purchases</span>
        </div>
      </div>
      <s-text color="subdued">No events yet</s-text>
      <div className={styles.acts}>
        <s-button variant={problem ? "primary" : "secondary"} commandFor={EDITOR_ID} command="--show" onClick={open}>
          {problem ? "Update token" : "Edit pixel"}
        </s-button>
      </div>
    </div>
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
      <s-text-field
        label="Test event code"
        value={testEventCode}
        placeholder="TEST12345"
        details="Optional. Only while you test in Events Manager; clear it for real traffic."
        onInput={(e) => setTestEventCode(value(e))}
        onChange={(e) => setTestEventCode(value(e))}
      />
      {showCheck ? (
        showCheck.ok ? (
          <s-banner tone="success" heading="Meta found this pixel">
            {showCheck.pixel_name ?? "This pixel"}
            {showCheck.owner_name ? ` (owned by ${showCheck.owner_name})` : ""}. The token can read it.
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
