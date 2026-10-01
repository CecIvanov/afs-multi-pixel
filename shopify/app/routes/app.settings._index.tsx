import type { LoaderFunctionArgs } from "react-router";
import { authenticate } from "../shopify.server";

export const loader = async ({ request }: LoaderFunctionArgs) => {
  await authenticate.admin(request);
  return null;
};

export default function Settings() {
  return (
    <s-page heading="Settings">
      <s-section heading="Example settings">
        <s-paragraph>
          Replace this with your app's settings. The loader/action → server-module
          pattern and the contextual save bar are added as your first real form.
        </s-paragraph>
      </s-section>
    </s-page>
  );
}
