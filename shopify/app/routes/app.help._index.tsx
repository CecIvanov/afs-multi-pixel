import type { HeadersFunction, LoaderFunctionArgs } from "react-router";
import { boundary } from "@shopify/shopify-app-react-router/server";
import { useLoaderData } from "react-router";
import { authenticate } from "../shopify.server";
import { resolveSupportConfig } from "../support.server";
import { supportEmailMailtoUrl, supportViberChatUrl } from "../support.shared.mjs";
import { FAQ, HOWTO } from "../help-content";
import { withRequestContext } from "../request-context.server";

export const loader = async ({ request }: LoaderFunctionArgs) => {
  const { session } = await authenticate.admin(request);
  return withRequestContext(request, session.shop, async () => {
    const support = resolveSupportConfig();
    return {
      support,
      mailto: supportEmailMailtoUrl(support.email),
      viberUrl: support.viber.enabled ? supportViberChatUrl(support.viber.numberE164) : null,
      faq: FAQ,
      howto: HOWTO,
    };
  });
};

export default function Help() {
  const { support, mailto, viberUrl, faq, howto } = useLoaderData<typeof loader>();
  return (
    <s-page heading="Help">
      <s-section heading="Support">
        <s-paragraph>Need a hand? Reach us here — we reply the same business day.</s-paragraph>
        {support.email ? (
          <s-button href={mailto}>Email {support.email}</s-button>
        ) : null}
        {viberUrl ? (
          <s-paragraph>
            <s-button href={viberUrl} target="_blank">{support.viber.label}</s-button>
            {support.viber.display ? <s-text> {support.viber.display}</s-text> : null}
          </s-paragraph>
        ) : null}
      </s-section>

      <s-section heading="Frequently asked questions">
        {faq.map((item, i) => (
          <details key={i} style={{ borderBottom: "1px solid var(--s-color-border, #e1e3e5)", padding: "8px 0" }}>
            <summary style={{ cursor: "pointer", fontWeight: 600 }}>{item.q}</summary>
            <s-paragraph>{item.a}</s-paragraph>
          </details>
        ))}
      </s-section>

      <s-section heading="How-to guides">
        {howto.map((guide, i) => (
          <div key={i} style={{ marginBottom: 16 }}>
            <s-heading>{guide.title}</s-heading>
            <ol>
              {guide.steps.map((step, j) => (
                <li key={j}>{step}</li>
              ))}
            </ol>
          </div>
        ))}
      </s-section>
    </s-page>
  );
}

// Shopify's embedded-app headers (CSP frame-ancestors) on this document too.
export const headers: HeadersFunction = (headersArgs) => boundary.headers(headersArgs);
