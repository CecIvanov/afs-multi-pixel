import type { ActionFunctionArgs, LoaderFunctionArgs } from "react-router";
import { decryptEnvelope } from "../models/relay-crypto.server";
import { handleStorefrontEvent } from "../models/relay.server";
import prisma from "../db.server";

// Encrypted relay from the storefront (theme embed + Web Pixel). The browser sends a text/plain
// envelope with `no-cors`, so there's no preflight and nothing is returned to read.
const MAX_BODY = 32 * 1024;

export const action = async ({ request }: ActionFunctionArgs) => {
  const origin = request.headers.get("origin");
  const body = await request.text();
  if (body.length > MAX_BODY) return new Response(null, { status: 413 });

  let event: unknown;
  try {
    event = await decryptEnvelope(body);
  } catch (error) {
    await prisma.eventLog.create({
      data: {
        shop: "unknown",
        source: "storefront",
        eventName: "?",
        status: "rejected",
        detail: `could not decrypt: ${String(error).slice(0, 200)}`,
        origin: origin ?? undefined,
      },
    });
    return new Response(null, { status: 400 });
  }

  await handleStorefrontEvent(event, {
    origin,
    ip: request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() || undefined,
    userAgent: request.headers.get("user-agent") ?? undefined,
  });
  return new Response(null, { status: 204 });
};

export const loader = async (_args: LoaderFunctionArgs) => new Response(null, { status: 405 });
