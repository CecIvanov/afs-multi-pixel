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
