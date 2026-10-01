import type { HeadersFunction, LoaderFunctionArgs } from "react-router";
import { useLoaderData } from "react-router";
import { boundary } from "@shopify/shopify-app-react-router/server";
import { authenticate } from "../shopify.server";
import prisma from "../db.server";

export const loader = async ({ request }: LoaderFunctionArgs) => {
  const { session } = await authenticate.admin(request);
  const events = await prisma.eventLog.findMany({
    where: { shop: { in: [session.shop, "unknown"] } },
    orderBy: { id: "desc" },
    take: 100,
  });
  return {
    events: events.map((e) => ({ ...e, createdAt: e.createdAt.toISOString() })),
  };
};

const TONE: Record<string, "success" | "critical" | "warning" | "info" | "neutral"> = {
  sent: "success",
  error: "critical",
  rejected: "critical",
  waiting: "info",
  skipped: "warning",
};

export default function EventLog() {
  const { events } = useLoaderData<typeof loader>();

  return (
    <s-page heading="Event log">
      <s-section heading="Last 100 events received by the backend">
        {events.length === 0 ? (
          <s-paragraph>No events yet.</s-paragraph>
        ) : (
          <s-table>
            <s-table-header-row>
              <s-table-header>Time</s-table-header>
              <s-table-header>Event</s-table-header>
              <s-table-header>Status</s-table-header>
              <s-table-header>Market → pixel</s-table-header>
              <s-table-header>Event ID</s-table-header>
              <s-table-header>Detail</s-table-header>
            </s-table-header-row>
            <s-table-body>
              {events.map((e) => (
                <s-table-row key={e.id}>
                  <s-table-cell>{new Date(e.createdAt).toLocaleTimeString()}</s-table-cell>
                  <s-table-cell>
                    {e.eventName} <s-text color="subdued">({e.source})</s-text>
                  </s-table-cell>
                  <s-table-cell>
                    <s-badge tone={TONE[e.status] ?? "neutral"}>{e.status}</s-badge>
                  </s-table-cell>
                  <s-table-cell>
                    {e.marketId ?? "–"} → {e.pixelId ?? "–"}
                  </s-table-cell>
                  <s-table-cell>{e.eventId ?? "–"}</s-table-cell>
                  <s-table-cell>{e.detail ?? ""}</s-table-cell>
                </s-table-row>
              ))}
            </s-table-body>
          </s-table>
        )}
      </s-section>
    </s-page>
  );
}

export const headers: HeadersFunction = (headersArgs) => boundary.headers(headersArgs);
