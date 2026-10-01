import { createHash } from "node:crypto";

// Meta Conversions API client: one event, one pixel, that pixel's own access token.
// https://developers.facebook.com/docs/marketing-api/conversions-api

const GRAPH_VERSION = "v26.0";

export type UserData = {
  client_ip_address?: string;
  client_user_agent?: string;
  fbp?: string;
  fbc?: string;
  em?: string;
  ph?: string;
  fn?: string;
  ln?: string;
  ct?: string;
  st?: string;
  zp?: string;
  country?: string;
  external_id?: string;
};

export type CustomData = {
  content_ids?: string[];
  content_type?: string;
  content_name?: string;
  content_category?: string;
  value?: number;
  currency?: string;
  num_items?: number;
  search_string?: string;
  order_id?: string;
};

export type ServerEvent = {
  event_name: string;
  event_id: string;
  event_time: number; // unix seconds
  event_source_url?: string;
  action_source: "website";
  user_data: UserData;
  custom_data?: CustomData;
};

export type CapiResult = { ok: boolean; detail: string };

export async function sendToCapi(
  pixelId: string,
  accessToken: string,
  event: ServerEvent,
  testEventCode?: string | null,
): Promise<CapiResult> {
  const body: Record<string, unknown> = { data: [event], access_token: accessToken };
  if (testEventCode) body.test_event_code = testEventCode;

  try {
    const response = await fetch(`https://graph.facebook.com/${GRAPH_VERSION}/${pixelId}/events`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const text = await response.text();
    return { ok: response.ok, detail: `${response.status} ${text.slice(0, 500)}` };
  } catch (error) {
    return { ok: false, detail: String(error) };
  }
}

// Meta's normalisation rules before SHA-256: https://developers.facebook.com/docs/marketing-api/conversions-api/parameters/customer-information-parameters
const sha256 = (value: string) => createHash("sha256").update(value).digest("hex");

const hashed = (value: string | null | undefined, normalise: (v: string) => string) => {
  const normalised = value ? normalise(value) : "";
  return normalised ? sha256(normalised) : undefined;
};

const lower = (v: string) => v.trim().toLowerCase();
const lettersOnly = (v: string) => v.toLowerCase().replace(/[^\p{L}]/gu, "");
const digitsOnly = (v: string) => v.replace(/\D/g, "");
const noSpaces = (v: string) => v.toLowerCase().replace(/\s/g, "");

export function hashCustomer(customer: {
  email?: string | null;
  phone?: string | null;
  firstName?: string | null;
  lastName?: string | null;
  city?: string | null;
  provinceCode?: string | null;
  zip?: string | null;
  countryCode?: string | null;
  customerId?: string | null;
}): UserData {
  return {
    em: hashed(customer.email, lower),
    ph: hashed(customer.phone, digitsOnly),
    fn: hashed(customer.firstName, lower),
    ln: hashed(customer.lastName, lower),
    ct: hashed(customer.city, lettersOnly),
    st: hashed(customer.provinceCode, lower),
    zp: hashed(customer.zip, noSpaces),
    country: hashed(customer.countryCode, lower),
    external_id: hashed(customer.customerId, lower),
  };
}

export const withoutEmpty = <T extends Record<string, unknown>>(value: T): T =>
  Object.fromEntries(
    Object.entries(value).filter(([, v]) => v !== undefined && v !== null && v !== ""),
  ) as T;
