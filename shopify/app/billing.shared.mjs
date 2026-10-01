// Pure plan semantics — mirrors backend/app/billing/plan_catalog.py so both
// languages classify/normalize identically. Functions take a `plans` array
// (from app.config.json billing.plans) so they stay pure + unit-testable. A
// parity test (Phase 4) guards drift against the Python side.

/** @param {Array<{handle:string,name?:string,rank?:number,shopifyPlanName?:string|null}>} plans */
export function rankOf(plans, handle) {
  const p = plans.find((x) => x.handle === handle);
  return p ? p.rank || 0 : 0;
}

export function classifyChange(plans, from, to) {
  if (!to || from === to) return "same";
  const f = rankOf(plans, from);
  const t = rankOf(plans, to);
  return t > f ? "upgrade" : t < f ? "downgrade" : "same";
}

/** Map a Shopify plan / display name to a canonical handle, or null. */
export function normalizeShopifyPlanName(plans, raw) {
  const norm = String(raw || "").trim().toLowerCase();
  if (!norm) return null;
  for (const p of plans) {
    const candidates = new Set([p.handle.toLowerCase(), (p.name || "").toLowerCase()]);
    if (p.shopifyPlanName) candidates.add(p.shopifyPlanName.toLowerCase());
    if (candidates.has(norm)) return p.handle;
  }
  for (const p of [...plans].sort((a, b) => (b.rank || 0) - (a.rank || 0))) {
    if (norm.includes(p.handle.toLowerCase()) || (p.name && norm.includes(p.name.toLowerCase()))) {
      return p.handle;
    }
  }
  return null;
}
