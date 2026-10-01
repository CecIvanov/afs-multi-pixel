import type { Config } from "@react-router/dev/config";

export default {
  future: {
    // Enables route `middleware` (app/root.tsx requestContextMiddleware) so every
    // loader/action/resource route/webhook gets a request-scoped context and all
    // UI logs carry a requestId.
    v8_middleware: true,
  },
} satisfies Config;
