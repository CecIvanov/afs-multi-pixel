import { createLogger, type LogContext } from "../../packages/logger/src/index.ts";
import { getRequestId, getRequestShop } from "./request-context.server.ts";

export const rootLogger = createLogger({
  baseContext: { component: "ui", service: "ui", env: process.env.APP_ENV ?? "development" },
});

function contextualFields(fields: LogContext = {}): LogContext {
  const requestId = getRequestId();
  const shop = getRequestShop();
  return {
    ...(requestId ? { requestId } : {}),
    ...(shop ? { shop } : {}),
    ...fields,
  };
}

export function logInfo(event: string, fields: LogContext = {}) {
  rootLogger.info(event, contextualFields(fields));
}
export function logWarn(event: string, fields: LogContext = {}) {
  rootLogger.warn(event, contextualFields(fields));
}
export function logError(event: string, error: unknown, fields: LogContext = {}) {
  rootLogger.error(event, error, contextualFields(fields));
}

export { createLogger };
