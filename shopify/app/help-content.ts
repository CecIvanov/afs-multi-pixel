// Help-page content. Edit these for your app — they render on /app/help under the
// FAQ and How-to sections. (Support contact comes from app.config.json's `support`
// block; see support.server.ts.) Keep answers short and task-focused.

export type FaqItem = { q: string; a: string };
export type HowtoItem = { title: string; steps: string[] };

export const FAQ: FaqItem[] = [
  {
    q: "How do I change my plan?",
    a: "Open Billing in the app, choose a plan, and confirm on Shopify's checkout. Changes reconcile automatically.",
  },
  {
    q: "How is my usage counted?",
    a: "Usage resets at the start of each billing period. You can see the current period's usage on the Billing page.",
  },
  {
    q: "How do I get help?",
    a: "Use the contact options in the Support section below — we reply on the same business day.",
  },
];

export const HOWTO: HowtoItem[] = [
  {
    title: "Install and set up the app",
    steps: [
      "Install the app on your store from the Shopify App Store.",
      "Open the app — it configures your account automatically on first load.",
      "Review Settings and Billing to pick the plan that fits you.",
    ],
  },
  {
    title: "Contact support",
    steps: [
      "Open the Help page (this screen).",
      "Email us, or tap the floating chat button if your merchant has it enabled.",
    ],
  },
];
