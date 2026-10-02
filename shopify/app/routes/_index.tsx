import { redirect, type LoaderFunctionArgs } from "react-router";

export const loader = async ({ request }: LoaderFunctionArgs) => {
  const url = new URL(request.url);
  // When Shopify launches the app it includes ?shop=... — hand off to OAuth.
  if (url.searchParams.get("shop")) {
    throw redirect(`/app?${url.searchParams.toString()}`);
  }
  return null;
};

// The public landing page. Installation starts only from Shopify (App Store 2.3.1):
// no shop-domain form here.
export default function Index() {
  return (
    <main style={{ fontFamily: "Inter, system-ui, sans-serif", maxWidth: 560, margin: "80px auto", padding: 24 }}>
      <h1>AFS Multi Pixel</h1>
      <p>A separate Meta pixel for every Shopify Market, with browser and server events.</p>
      <p>Install AFS Multi Pixel from the Shopify App Store, then open it from your Shopify admin.</p>
      <p>
        <a href="/privacy">Privacy policy</a> · <a href="/terms">Terms of service</a>
      </p>
    </main>
  );
}
