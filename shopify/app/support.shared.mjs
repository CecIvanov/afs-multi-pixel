// Pure support-channel helpers (no I/O) so node --test covers the deep link, the
// enabled gate, and the anchor safety attrs — the parts most likely to regress.

/** Coerce an env string / boolean to a boolean. "1"/"true"/"yes" => true. */
export function isTruthy(value) {
  return ["1", "true", "yes", "on"].includes(String(value ?? "").trim().toLowerCase());
}

/** Viber deep link. Number must be E.164 WITHOUT the leading '+'. */
export function supportViberChatUrl(numberE164) {
  const digits = String(numberE164 || "").replace(/[^0-9]/g, "");
  return digits ? `viber://chat?number=${digits}` : "";
}

export function supportEmailMailtoUrl(email) {
  return email ? `mailto:${email}` : "";
}

/** The Viber floating button shows only when explicitly enabled AND given a number. */
export function isViberFabEnabled({ enabled, numberE164 } = {}) {
  return isTruthy(enabled) && Boolean(supportViberChatUrl(numberE164));
}

/** Anchor attrs for the FAB — throwaway context so the Viber handoff never
 *  clobbers in-app admin state, and no referrer leak. */
export function viberFabAnchorAttrs(numberE164) {
  return { href: supportViberChatUrl(numberE164), target: "_blank", rel: "noopener noreferrer" };
}
