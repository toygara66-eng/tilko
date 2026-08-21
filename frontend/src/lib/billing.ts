import type { SubscriptionPlan } from "@/lib/api";

export const FALLBACK_PLANS: SubscriptionPlan[] = [
  {
    id: "tilko_pro_monthly",
    label: "Aylık Tilko Pro",
    period: "monthly",
    days: 31,
    price_try: 149,
    price_label: "149 TL / ay",
  },
  {
    id: "tilko_pro_yearly",
    label: "Yıllık Tilko Pro",
    period: "yearly",
    days: 366,
    price_try: 990,
    price_label: "990 TL / yıl",
  },
];

export type PlayPurchaseResult = {
  purchaseToken: string;
  productId: string;
  orderId: string;
  platform: "android" | "sandbox";
};

type PlayBridge = {
  launch: (productId: string) => Promise<{
    purchaseToken: string;
    productId?: string;
    orderId?: string;
  }>;
};

declare global {
  interface Window {
    TilkoPlayBilling?: PlayBridge;
  }
}

export function hasNativePlayBilling() {
  return typeof window !== "undefined" && typeof window.TilkoPlayBilling?.launch === "function";
}

export function sandboxToken(userId: string, productId: string) {
  const nonce =
    typeof crypto !== "undefined" && crypto.randomUUID
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `gp_sandbox.${userId}.${productId}.${nonce}`;
}

export async function launchPlayPurchase(
  userId: string,
  productId: string,
): Promise<PlayPurchaseResult> {
  if (hasNativePlayBilling() && window.TilkoPlayBilling) {
    const native = await window.TilkoPlayBilling.launch(productId);
    const token = String(native.purchaseToken || "").trim();
    if (!token) {
      throw new Error("Google Play token boş döndü.");
    }
    return {
      purchaseToken: token,
      productId: native.productId || productId,
      orderId: native.orderId || "",
      platform: "android",
    };
  }
  await new Promise((resolve) => window.setTimeout(resolve, 700));
  return {
    purchaseToken: sandboxToken(userId, productId),
    productId,
    orderId: `GPA.TEST-${Date.now()}`,
    platform: "sandbox",
  };
}
