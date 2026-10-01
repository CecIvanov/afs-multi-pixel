import { redirect, type LoaderFunctionArgs, Form, useLoaderData } from "react-router";
import { login } from "../shopify.server";

export const loader = async ({ request }: LoaderFunctionArgs) => {
  const url = new URL(request.url);
  // When Shopify launches the app it includes ?shop=... — hand off to OAuth.
  if (url.searchParams.get("shop")) {
    throw redirect(`/app?${url.searchParams.toString()}`);
  }
  return { showForm: Boolean(login) };
};

export default function Index() {
  const { showForm } = useLoaderData<typeof loader>();
  return (
    <main style={{ fontFamily: "Inter, system-ui, sans-serif", maxWidth: 480, margin: "80px auto", padding: 24 }}>
      <h1>Shopify App</h1>
      <p>A template app. Install it on a store to get started.</p>
      {showForm && (
        <Form method="post" action="/auth/login">
          <label style={{ display: "block", marginBottom: 8 }}>
            Shop domain
            <input type="text" name="shop" placeholder="my-shop.myshopify.com" style={{ display: "block", width: "100%", padding: 8 }} />
          </label>
          <button type="submit">Log in</button>
        </Form>
      )}
    </main>
  );
}
