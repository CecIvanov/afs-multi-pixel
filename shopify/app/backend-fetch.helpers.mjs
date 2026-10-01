// Helpers for the Node -> Python backend client. Pure functions (no I/O) so they
// are unit-testable with node --test.

export class BackendRequestError extends Error {
  /** @param {number} status @param {string} detail @param {{code?: string}} [opts] */
  constructor(status, detail, opts = {}) {
    super(`Backend request failed (${status}): ${detail}`);
    this.name = "BackendRequestError";
    this.status = status;
    this.detail = detail;
    this.code = opts.code;
  }
}

/** A thrown Response with a 3xx status is a redirect, not an error. */
export function isRedirectResponse(value) {
  return value instanceof Response && value.status >= 300 && value.status < 400;
}

/** Best-effort extraction of a { detail } message from a JSON error body. */
export function parseBackendErrorDetail(text) {
  if (!text) return "";
  try {
    const parsed = JSON.parse(text);
    if (parsed && typeof parsed.detail === "string") return parsed.detail;
    if (parsed && typeof parsed.message === "string") return parsed.message;
  } catch {
    // not JSON — fall through
  }
  return text;
}

export function isBackendTenantNotFoundError(error) {
  return error instanceof BackendRequestError && (error.status === 404 || error.code === "TENANT_NOT_FOUND");
}

/** A handled 404 (tenant-not-found) should not be logged as a failure. */
export function shouldLogBackendRequestFailure(status, _detail) {
  return status !== 404;
}
