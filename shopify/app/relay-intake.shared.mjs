// The public Relay endpoint (POST /api/events, spec §3.2). The storefront sends an
// encrypted envelope as text/plain with `no-cors`, so it can't read the answer:
// this hands the envelope to the backend (which decrypts, validates and stores it)
// and answers 204. Pure apart from the injected `forward`, so node --test covers it.

export const MAX_RELAY_BYTES = 32 * 1024;

/** The shopper's IP behind Caddy: the first X-Forwarded-For hop. */
export function clientIp(headers) {
  const forwarded = headers.get("x-forwarded-for");
  if (forwarded) return forwarded.split(",")[0].trim() || null;
  return headers.get("x-real-ip") || null;
}

/**
 * @param {Request} request
 * @param {{ forward: (relay: { body: string, origin: string | null, ip: string | null, user_agent: string | null }) => Promise<unknown>,
 *           logError?: (name: string, error: unknown) => void }} deps
 */
export async function receiveRelay(request, { forward, logError = () => {} }) {
  const declared = Number(request.headers.get("content-length") || 0);
  if (declared > MAX_RELAY_BYTES) return new Response(null, { status: 413 });
  const body = await request.text();
  if (body.length > MAX_RELAY_BYTES) return new Response(null, { status: 413 });

  try {
    await forward({
      body,
      origin: request.headers.get("origin"),
      ip: clientIp(request.headers),
      user_agent: request.headers.get("user-agent"),
    });
  } catch (error) {
    logError("relay_forward_failed", error);
  }
  return new Response(null, { status: 204 });
}
