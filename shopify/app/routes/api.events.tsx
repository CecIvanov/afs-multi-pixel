import type { ActionFunctionArgs } from "react-router";
import { forwardRelay } from "../backend.server";
import { logError } from "../logger.server";
import { receiveRelay } from "../relay-intake.shared.mjs";

// Public: the theme app embed and the Web Pixel post encrypted Relays here.
export const action = ({ request }: ActionFunctionArgs) =>
  receiveRelay(request, { forward: forwardRelay, logError: (name, error) => logError(name, error) });

export const loader = () => new Response(null, { status: 405 });
