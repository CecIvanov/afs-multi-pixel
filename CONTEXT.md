# Multi-Pixel

A public Shopify app that sends a store's Meta pixel events to a different Meta pixel for each Shopify Market, so that Meta's ad optimisation learns which products are popular in each market separately.

## Language

**Market**:
A Shopify Market configured in the merchant's store (for example "Romania" or "Bulgaria"), which decides the storefront experience a shopper gets.
_Avoid_: region, country (a Market can span several countries)

**Market Pixel**:
The Meta pixel that the merchant has assigned to a Market in our app.
_Avoid_: market pixel ID, per-market pixel

**Pixel Mapping**:
The merchant's full set of Market → Market Pixel assignments for one store.
_Avoid_: pixel config, market mapping

**Standard Funnel**:
Meta's standard e-commerce events that the app sends: PageView, ViewContent, Search, AddToCart, InitiateCheckout, AddPaymentInfo and Purchase.

**Official Meta App**:
Meta's own "Facebook & Instagram" Shopify sales channel, which sends every event to a single pixel.
_Avoid_: Meta channel, FB app

**Browser Event**:
A Standard Funnel event the shopper's browser sends to a Market Pixel (through Meta's pixel script or Meta's `/tr` endpoint).
_Avoid_: client event, pixel event

**Server Event**:
The same event sent by the app's backend to the Market Pixel through Meta's Conversions API, carrying the Browser Event's event ID so Meta keeps one of the two.
_Avoid_: CAPI event, backend event

**Relay**:
The encrypted copy of a Browser Event that the storefront sends to the app's backend, from which the Server Event is made.
_Avoid_: browser note, beacon

**Market Catalog**:
The Meta product catalog used for one Market's ads; its item `id` is the Shopify variant ID and its `item_group_id` the Shopify product ID.
_Avoid_: feed (the feed is the file that fills a catalog)
