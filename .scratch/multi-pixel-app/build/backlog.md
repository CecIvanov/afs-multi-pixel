# AFS Multi Pixel v1: build backlog (moved to GitHub)

On 2026-10-01 the backlog moved to GitHub Issues: parent issue [#13 AFS Multi Pixel v1 build](https://github.com/CecIvanov/afs-multi-pixel/issues/13), with each ticket as a sub-issue and blocking set with GitHub's issue dependencies. GitHub is the source of truth now; the local ticket files were removed (they're in git history before this commit).

| Old # | Issue | Title |
|---|---|---|
| 00 | [#1](https://github.com/CecIvanov/afs-multi-pixel/issues/1) | Set up the UAT App, the Production App, protected data access and the plan |
| 01 | [#2](https://github.com/CecIvanov/afs-multi-pixel/issues/2) | Start the production app on a clean branch with Postgres, Docker and two app configs |
| 02 | [#3](https://github.com/CecIvanov/afs-multi-pixel/issues/3) | Store every webhook, answer 200, and process it in the worker |
| 03 | [#4](https://github.com/CecIvanov/afs-multi-pixel/issues/4) | Sync Markets and let the merchant map pixel + token pairs on the Market health page |
| 04 | [#5](https://github.com/CecIvanov/afs-multi-pixel/issues/5) | Publish the Pixel Mapping, Relay key and endpoint to the storefront and checkout |
| 05 | [#6](https://github.com/CecIvanov/afs-multi-pixel/issues/6) | Send storefront events from the theme app embed, gated by consent |
| 06 | [#7](https://github.com/CecIvanov/afs-multi-pixel/issues/7) | Send AddToCart and checkout events from the strict Web Pixel |
| 07 | [#8](https://github.com/CecIvanov/afs-multi-pixel/issues/8) | Store Relays and send Server Events to the Conversions API from the worker |
| 08 | [#9](https://github.com/CecIvanov/afs-multi-pixel/issues/9) | Join the browser Purchase with orders/create and send the hashed Server Purchase |
| 09 | [#10](https://github.com/CecIvanov/afs-multi-pixel/issues/10) | Require the active subscription to the one paid plan |
| 10 | [#11](https://github.com/CecIvanov/afs-multi-pixel/issues/11) | Add daily jobs, backups and the UAT release checklist |
| 11 | [#12](https://github.com/CecIvanov/afs-multi-pixel/issues/12) | Prepare and submit the Production App to the App Store |
