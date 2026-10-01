type CustomData = Record<string, unknown>;
export declare const numericId: (id: string | null | undefined) => string | null;
export declare function addToCartData(line: unknown): CustomData;
export declare function checkoutData(checkout: unknown): CustomData;
export declare function purchaseData(checkout: unknown): CustomData;
export declare function purchaseEventId(checkout: unknown): string | null;
export declare function trQuery(input: {
  pixelId: string;
  event: string;
  eventId: string;
  url: string;
  referrer?: string;
  timestamp: number;
  fbp?: string;
  fbc?: string;
  data: CustomData;
}): string;
