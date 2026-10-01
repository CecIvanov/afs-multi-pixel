# How does the merchant connect Meta in v1: Meta login or validated manual entry?

Type: grilling
Label: wayfinder:grilling
Status: resolved
Assignee: Tsvetan Ivanov
Blocked by: 04
Map: [AFS Multi Pixel map](../map.md)

## Question

Given the Meta connection research: does v1 use Facebook Login for Business to list pixels and create CAPI tokens, validated manual entry of pixel ID + token, or both? Cover token storage, expiry and revocation handling, and how Meta errors reach the merchant.

## Answer

**Manual entry; no Meta login in v1 (the user's call, 2026-10-01).** For each Market the merchant maps, the **pixel ID and its Conversions API token are a mandatory pair**: a Market can't have a Market Pixel without a token. A Market with no pair still sends nothing, as in the POC. This avoids the weeks of Meta App Review, Business Verification and Tech Provider checks (see [How can a third-party app connect a merchant's Meta account to list pixels and obtain Conversions API tokens?](04-meta-connection-options.md)), and matches how almost every competitor sets up.

Carried forward, not decided here:
- Validating the pair on save (the research suggests `GET /<pixel>?fields=id,name,owner_business,is_unavailable`; whether an Events Manager token can read its pixel needs a test) and how Meta send errors reach the merchant belong in [How does the merchant set up and maintain their Pixel Mapping in the admin?](14-onboarding-and-mapping-ux.md).
- Token encryption at rest belongs in [Where does production run, and how are its data and secrets stored?](12-hosting-data-secrets.md) (AES-GCM helper from AFS).
