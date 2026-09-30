# What are the documented ways to fire a Purchase from the thank-you page?

Type: research
Label: wayfinder:research
Status: open
Map: [Multi-Pixel map](../map.md)

## Question

This is the backstop in case the Web Pixel route (ticket 01) can't deliver a Market-aware Purchase. What mechanisms does Shopify currently offer a **public app** to run code or send data on the **thank-you / order status page** after the native checkout?

- The status of "additional scripts" and `checkout.liquid` on the thank-you and order status pages (deprecation and sunset dates for Plus and non-Plus).
- Can Checkout UI extensions on the thank-you page (`purchase.thank-you.*` targets) make network calls to third parties or load scripts? What order and market or localization data can they read?
- Any other option available to a public app (app pixels via Customer Events, order status page extensions), and what each needs (Plus only? protected customer data approval?).

Answer with primary sources (shopify.dev, Shopify changelog, help center).
