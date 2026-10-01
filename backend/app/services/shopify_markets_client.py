"""Fetch every Market of a shop from the Admin API (``read_markets``)."""

from __future__ import annotations

from app.models import Tenant
from app.services.market_service import ShopMarket, parse_market_node
from app.services.shopify_shop_info_service import admin_graphql

# No type filter: B2B and Draft Markets are listed and labelled like any other (spec §4).
MARKETS_QUERY = """
query MultiPixelMarkets($after: String) {
  markets(first: 100, after: $after) {
    nodes {
      id
      name
      type
      status
      conditions {
        regionsCondition {
          regions(first: 50) { nodes { name } }
        }
      }
    }
    pageInfo { hasNextPage endCursor }
  }
}
"""


def fetch_shop_markets(tenant: Tenant) -> list[ShopMarket]:
    markets: list[ShopMarket] = []
    after: str | None = None
    while True:
        payload = admin_graphql(
            shop_domain=tenant.shop_domain,
            access_token=tenant.access_token or "",
            query=MARKETS_QUERY,
            variables={"after": after},
        )
        connection = (payload.get("data") or {}).get("markets") or {}
        markets.extend(parse_market_node(node) for node in connection.get("nodes") or [])
        page = connection.get("pageInfo") or {}
        if not page.get("hasNextPage"):
            return markets
        after = page.get("endCursor")
