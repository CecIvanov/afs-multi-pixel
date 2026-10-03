import { useEffect } from "react";

/** Opens Shopify's plan page over the admin (App Bridge handles "_top"). Used on
 *  in-app navigations, where a server redirect() answers 401. */
export function GoToShopifyPlans({ url }: { url: string }) {
  useEffect(() => {
    open(url, "_top");
  }, [url]);
  return null;
}
