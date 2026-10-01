// The one paid plan (spec §1, §5): the app knows only its exact name and checks
// that the shop's subscription to it is active. Pure, so node --test covers it.

/**
 * @param {Array<{ name: string, status: string }> | null | undefined} subscriptions
 * @param {string} planName
 */
export function hasActivePlan(subscriptions, planName) {
  return (subscriptions ?? []).some((s) => s.name === planName && String(s.status).toUpperCase() === "ACTIVE");
}
