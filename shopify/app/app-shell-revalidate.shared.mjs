// When the app shell loader (routes/app.tsx) re-runs — ported from BG Delivery.
// Pure, so node --test covers it; app.tsx's `shouldRevalidate` delegates here.
//
// The shell loader syncs the tenant, reads the plan from Shopify's Partner API
// and the backend, and lists the Markets. React Router re-runs parent loaders on
// client navigations by default, which repeated all of that on every click. Its
// data (API key, plan gate, held-Market banner) doesn't change on a plain
// navigation, so that skips it.

/** True for a data-changing submission (anything that is not a GET). */
export function isMutation(formMethod) {
  return Boolean(formMethod) && String(formMethod).toUpperCase() !== "GET";
}

/** The merchant is back from Shopify's plan page: the plan gate must re-run. */
export function hasBillingRedirectParams(searchParams) {
  if (!searchParams || typeof searchParams.has !== "function") return false;
  return searchParams.has("plan_handle") || searchParams.has("charge_id");
}

/**
 * - back from Shopify billing → always (the plan just changed)
 * - any save (non-GET) → always (a Market save can change the held-Market banner)
 * - same path (revalidator.revalidate()) → the framework default
 * - a plain navigation to another route → skip
 */
export function shouldRevalidateAppShell({
  formMethod,
  currentPathname,
  nextPathname,
  nextSearchParams,
  defaultShouldRevalidate = true,
}) {
  if (hasBillingRedirectParams(nextSearchParams)) return true;
  if (isMutation(formMethod)) return true;
  if (currentPathname === nextPathname) return defaultShouldRevalidate;
  return false;
}
