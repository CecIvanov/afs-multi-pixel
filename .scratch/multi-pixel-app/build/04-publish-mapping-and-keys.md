# Publish the Pixel Mapping, Relay key and endpoint to the storefront and checkout

Type: AFK
Status: open
Assignee:
Blocked by: 03
Spec: §3.2, §5, §6 (`AppKey`), §8
Backlog: [backlog.md](backlog.md)

## What

Generate the Relay RSA key pair once (private key encrypted in `AppKey`). On every mapping save and on app start, mirror the mapping, Relay endpoint and public key to the app-owned metafield `multi_pixel.mapping` and to the Web Pixel's settings (create the Web Pixel on install with `write_pixels`). Keep the shop's storefront domain allowlist (fetched on install, app open and daily).

## Acceptance criteria

- [ ] Restarting or redeploying the app republishes the key and endpoint with no merchant action
- [ ] The metafield and Web Pixel settings match the database after every save
- [ ] The shop's domains, including a newly added custom domain, reach the allowlist within a day or on app open
