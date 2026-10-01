import { isViberFabEnabled } from "./support.shared.mjs";

// Support config resolved from env (compose exports these from app.config.json's
// `support` block). Server-only so it can be handed to loaders/components.
export type SupportConfig = {
  email: string;
  viber: {
    enabled: boolean;
    numberE164: string;
    display: string;
    label: string;
  };
};

export function resolveSupportConfig(env = process.env): SupportConfig {
  const numberE164 = env.SUPPORT_VIBER_NUMBER || "";
  const enabled = isViberFabEnabled({ enabled: env.SUPPORT_VIBER_ENABLED, numberE164 });
  return {
    email: env.SUPPORT_EMAIL || "",
    viber: {
      enabled,
      numberE164,
      display: env.SUPPORT_VIBER_DISPLAY || "",
      label: env.SUPPORT_VIBER_LABEL || "Chat on Viber",
    },
  };
}
