// Help-page content (spec §10): the setup guide, checking events in Events Manager
// and the FAQ. Rendered on /app/help; the support contact comes from
// app.config.json's `support` block (see support.server.ts).

export type FaqItem = { q: string; a: string };
export type HowtoItem = { title: string; steps: string[] };

export const FAQ: FaqItem[] = [
  {
    q: "What does AFS Multi Pixel do?",
    a: "It sends each shopper's Meta events (PageView, ViewContent, Search, AddToCart, InitiateCheckout, AddPaymentInfo, Purchase) to the pixel of the Market they're shopping in, from the browser and through the Conversions API, deduplicated. Each Market gets its own Pixel, Market Catalog and ads.",
  },
  {
    q: "Can I keep the Official Meta app (Facebook & Instagram) installed?",
    a: "Yes, but don't use the same pixel in both. If the Official Meta app and AFS Multi Pixel send to the same pixel, every event is counted twice. Give AFS Multi Pixel its own pixel per Market, or turn off the Official Meta app's data sharing for that pixel.",
  },
  {
    q: "What happens in a Market without a pixel?",
    a: "Nothing is sent for shoppers in that Market. There's no fallback pixel, so add a pixel to every Market you advertise in.",
  },
  {
    q: "Why do I need a Conversions API token for every pixel?",
    a: "Every mapped Market sends browser and server events. The token lets the app send the server copy, which Meta matches to the browser event by event ID and counts once.",
  },
  {
    q: "What about cookie consent?",
    a: "Nothing loads and nothing is sent until the shopper allows marketing and the sale of data in your store's cookie banner. Set the banner up in Settings → Customer privacy.",
  },
  {
    q: "What does \"Token problem\" mean?",
    a: "Meta rejected the Market's Conversions API token (it expired or was revoked). Browser events keep going; server events wait. Paste a new token with \"Update token\" and the waiting events from the last 7 days are sent.",
  },
  {
    q: "Which customer data does the app use?",
    a: "Only for the server Purchase: the order's email, phone, name and address, hashed (SHA-256) before they're stored or sent, and only when the shopper gave marketing consent. Event logs are kept 30 days.",
  },
];

export const HOWTO: HowtoItem[] = [
  {
    title: "Set up AFS Multi Pixel",
    steps: [
      "On the Markets page, choose \"Turn on the app embed\" and save the theme editor.",
      "In Meta Events Manager, create or pick one pixel (dataset) per Market, and copy its ID.",
      "In the pixel's Settings → Conversions API, generate an access token.",
      "In the app, choose \"Add pixel\" on the Market's tile, paste the pixel ID and the token, choose \"Check with Meta\", then Save.",
      "Repeat for every Market you advertise in.",
      "Make sure your store's cookie banner asks for consent (Settings → Customer privacy).",
    ],
  },
  {
    title: "Check events in Meta Events Manager",
    steps: [
      "Once the pixel is saved, choose \"Edit pixel\" on the Market's tile, add a test event code from Events Manager → Test events, and save.",
      "Visit your store on the Market's domain, allow cookies, view a product, add it to the cart and check out.",
      "In Test events, each event should appear once, received from both Browser and Server.",
      "Repeat for each Market and check that each pixel only gets its own Market's events.",
      "Clear the test event code when you're done, then tick \"I checked Events Manager\" on the Markets page.",
    ],
  },
  {
    title: "Contact support",
    steps: ["Email us using the button in the Support section. We reply on the same business day."],
  },
];
