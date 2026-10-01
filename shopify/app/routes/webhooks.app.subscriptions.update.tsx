import { webhookAction } from "../webhooks.server";

// app_subscriptions/update: stored, then the worker updates whether the shop's
// subscription to the one plan is active (Relays stop without it).
export const action = webhookAction;
