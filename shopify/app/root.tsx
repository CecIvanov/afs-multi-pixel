import { isRouteErrorResponse, Links, Meta, Outlet, Scripts, ScrollRestoration, useRouteError } from "react-router";
import { requestContextMiddleware } from "./request-context.server";

// Establishes the per-request context (requestId, ui.request.* logs, X-Request-Id
// header) for the ENTIRE route tree. Server-only export (stripped from the client
// bundle). Requires future.v8_middleware (react-router.config.ts).
export const middleware = [requestContextMiddleware];

export default function App() {
  return (
    <html lang="en">
      <head>
        <meta charSet="utf-8" />
        <meta name="viewport" content="width=device-width,initial-scale=1" />
        <link rel="preconnect" href="https://cdn.shopify.com/" />
        <link rel="stylesheet" href="https://cdn.shopify.com/static/fonts/inter/v4/styles.css" />
        <Meta />
        <Links />
      </head>
      <body>
        <Outlet />
        <ScrollRestoration />
        <Scripts />
      </body>
    </html>
  );
}

// Last resort for an error no route handled (routes/app.tsx re-throws anything
// that isn't one of Shopify's responses): a plain page with a way out, instead
// of React Router's bare "Unexpected Application Error".
export function ErrorBoundary() {
  const error = useRouteError();
  const notFound = isRouteErrorResponse(error) && error.status === 404;
  return (
    <html lang="en">
      <head>
        <meta charSet="utf-8" />
        <meta name="viewport" content="width=device-width,initial-scale=1" />
        <title>AFS Multi Pixel</title>
        <Meta />
        <Links />
      </head>
      <body style={{ fontFamily: "Inter, system-ui, sans-serif", margin: 0, background: "#f1f1f1" }}>
        <main
          style={{ maxWidth: 520, margin: "64px auto", padding: 24, background: "#fff", borderRadius: 12 }}
          role="alert"
        >
          <h1 style={{ fontSize: 20, margin: "0 0 8px" }}>
            {notFound ? "This page doesn't exist" : "Something went wrong"}
          </h1>
          <p style={{ margin: "0 0 16px", color: "#4a4a4a" }}>
            {notFound
              ? "Open AFS Multi Pixel again from your Shopify admin."
              : "AFS Multi Pixel couldn't load this page. Reload to try again; your Markets and pixels are safe."}
          </p>
          <button
            type="button"
            onClick={() => window.location.reload()}
            style={{ padding: "8px 16px", borderRadius: 8, border: "1px solid #8a8a8a", background: "#303030", color: "#fff", cursor: "pointer" }}
          >
            Reload
          </button>
        </main>
        <Scripts />
      </body>
    </html>
  );
}
