# What do existing multi-pixel and Conversions API apps on the Shopify App Store offer and charge?

Type: research
Label: wayfinder:research
Status: resolved
Assignee: Tsvetan Ivanov (research subagent)
Map: [AFS Multi Pixel map](../map.md)

## Question

Survey the Shopify App Store apps that send Meta pixel events to several pixels or offer CAPI (multi-pixel, server-side tracking apps). For each: per-Market or per-country routing (yes/no, how), CAPI included, other platforms, setup method (Meta login vs manual), pricing model and price points, review count and rating, Built for Shopify badge. Note gaps our per-Market routing + AFS catalog fit could own.

## Answer

Findings: branch `research/competitors`, file `research/competitors.md` (15 apps surveyed).

- **Routing by Market or country already exists, but rarely as the core product:**
  - Omega has Shopify Markets routing on its top tier only ($20.99–$99.99/mo, 4.8 from 989 reviews, BFS).
  - OC Meta Pixel lists "Markets" targeting with no documented mechanism ($14.99/$24.99, 5.0 from 108, BFS).
  - Zotek routes by country, not Market, from $29.99 ($12.99–$69.99, 5.0 from 166, BFS).
  - WeltPixel routes by Market in browser and server, "best-effort", bundled with nine platforms ($39 flat, 5.0 from 11, BFS).
  - Elevar routes per-Market destinations ($225–$1,250/mo).
- **Plain multi-pixel/CAPI apps** (Trackify, Pixee, Nabu, Pixelfy, etc.) cost mostly $5–$49/mo. The Official Meta App is free, single pixel, Facebook login, and rated 3.9 from 5,719 reviews.
- **Setup:** almost everyone uses a pasted pixel ID and a hand-made CAPI token. Meta login is rare.
- **Gaps we could own:** per-Market routing as the core product at an entry price; documented Browser + Server Event to the same Market Pixel with dedup; an event shape that matches the Official Meta App so Market Catalogs keep matching (no competitor claims it); pairing with AFS Market Catalogs; Meta-login setup.
- **Uncertain:** which Omega price includes Market targeting (plan names differ between its listing and help centre); how OC routes; whether any competitor matches catalog `content_ids`.
