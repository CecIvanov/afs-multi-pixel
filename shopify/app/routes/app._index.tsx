import type { LoaderFunctionArgs } from "react-router";
import { useLoaderData } from "react-router";
import { authenticate } from "../shopify.server";
import { getTenantByShop } from "../backend.server";
import { withRequestContext } from "../request-context.server";
import { logError } from "../logger.server";

export const loader = async ({ request }: LoaderFunctionArgs) => {
  const { session } = await authenticate.admin(request);
  return withRequestContext(request, session.shop, async () => {
    // Read the tenant back from the backend — proves the install round-trip.
    let tenant = null;
    try {
      tenant = await getTenantByShop(session.shop);
    } catch (error) {
      logError("app_index_tenant_fetch_failed", error, { shop: session.shop });
    }
    return { shop: session.shop, tenant };
  });
};

export default function Home() {
  const { shop, tenant } = useLoaderData<typeof loader>();
  return (
    <s-page heading="Home">
      <s-section heading="This store">
        <s-paragraph>Signed in as {shop}.</s-paragraph>
        {tenant ? (
          <>
            <s-paragraph>Tenant id: {tenant.id}</s-paragraph>
            <s-paragraph>
              Status: <s-badge tone={tenant.status === "active" ? "success" : "warning"}>{tenant.status}</s-badge>
            </s-paragraph>
            <s-paragraph>Plan: {tenant.plan_handle ?? "—"}</s-paragraph>
          </>
        ) : (
          <s-banner tone="warning" heading="Backend not ready">
            The backend tenant isn't available yet. Reload in a moment — install heals on the next navigation.
          </s-banner>
        )}
      </s-section>
    </s-page>
  );
}
