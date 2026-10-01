# What does a paid app do about the Official Meta App sending to the same pixels?

Type: grilling
Label: wayfinder:grilling
Status: resolved
Assignee: Tsvetan Ivanov
Blocked by: 07
Map: [AFS Multi Pixel map](../map.md)

## Question

The POC said misconfiguration is the merchant's problem. For a paid public app, which stance do we take: document it, detect and warn, or block? What do we tell merchants to set in the Official Meta App (for example data sharing off while keeping catalog sync)?

## Answer

**The merchant's configuration, not the app's problem (the user's call, 2026-10-01).** The app lets the merchant set their own pixel per Market. If they reuse the Official Meta App's pixel and double counting follows, that's a merchant configuration issue. The app doesn't detect, warn or block. The POC stance carries over unchanged.
