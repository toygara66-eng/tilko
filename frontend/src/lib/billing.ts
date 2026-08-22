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

type PlayNative = {
  launch: (productId: string) => void;
  restore?: () => void;
};

declare global {
  interface Window {
    TilkoPlayBilling?: PlayBridge;
    TilkoPlayBillingNative?: PlayNative;
    __tilkoBillingDone?: (payload: {
      purchaseToken?: string;
      productId?: string;
      orderId?: string;
      error?: string;
    }) => void;
  }
}

let bridgeReady = false;

/** Android native köprüsünü Promise API’ye sarar. */
export function installPlayBillingBridge() {
  if (typeof window === "undefined" || bridgeReady) return;
  const native = window.TilkoPlayBillingNative;
  if (!native || typeof native.launch !== "function") return;
  window.TilkoPlayBilling = {
    launch: (productId: string) =>
      new Promise((resolve, reject) => {
        const timer = window.setTimeout(() => {
          reject(new Error("Google Play ödeme zaman aşımı"));
        }, 180_000);
        window.__tilkoBillingDone = (payload) => {
          window.clearTimeout(timer);
          window.__tilkoBillingDone = undefined;
          if (payload?.error) {
            reject(new Error(payload.error));
            return;
          }
          const token = String(payload?.purchaseToken || "").trim();
          if (!token) {
            reject(new Error("Google Play token boş döndü."));
            return;
          }
          resolve({
            purchaseToken: token,
            productId: payload.productId || productId,
            orderId: payload.orderId || "",
          });
        };
        try {
          native.launch(productId);
        } catch (err) {
          window.clearTimeout(timer);
          window.__tilkoBillingDone = undefined;
          reject(err instanceof Error ? err : new Error("Play Billing açılamadı"));
        }
      }),
  };
  bridgeReady = true;
}

function nativePurchaseCall(
  run: (native: PlayNative) => void,
  fallbackProductId: string,
): Promise<PlayPurchaseResult> {
  installPlayBillingBridge();
  const native = window.TilkoPlayBillingNative;
  if (!native) {
    return Promise.reject(new Error("Play Billing köprüsü yok"));
  }
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(() => {
      reject(new Error("Google Play zaman aşımı"));
    }, 180_000);
    window.__tilkoBillingDone = (payload) => {
      window.clearTimeout(timer);
      window.__tilkoBillingDone = undefined;
      if (payload?.error) {
        reject(new Error(payload.error));
        return;
      }
      const token = String(payload?.purchaseToken || "").trim();
      if (!token) {
        reject(new Error("Google Play token boş döndü."));
        return;
      }
      resolve({
        purchaseToken: token,
        productId: payload.productId || fallbackProductId,
        orderId: payload.orderId || "",
        platform: "android",
      });
    };
    try {
      run(native);
    } catch (err) {
      window.clearTimeout(timer);
      window.__tilkoBillingDone = undefined;
      reject(err instanceof Error ? err : new Error("Play Billing açılamadı"));
    }
  });
}

export async function restorePlayPurchase(
  fallbackProductId = "tilko_pro_monthly",
): Promise<PlayPurchaseResult> {
  installPlayBillingBridge();
  const native = window.TilkoPlayBillingNative;
  if (!native?.restore) {
    throw new Error("Geri yükleme yalnızca Android uygulamasında.");
  }
  return nativePurchaseCall((bridge) => bridge.restore!(), fallbackProductId);
}

export function hasNativePlayBilling() {
  if (typeof window === "undefined") return false;
  installPlayBillingBridge();
  return typeof window.TilkoPlayBilling?.launch === "function";
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
  installPlayBillingBridge();
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
  const allowSandbox =
    process.env.NEXT_PUBLIC_PLAY_BILLING_SANDBOX !== "false" &&
    process.env.NODE_ENV !== "production";
  if (!allowSandbox) {
    throw new Error(
      "Tilko Pro ödemesi Google Play üzerinden yapılır. Android uygulamasını Play Store’dan aç.",
    );
  }
  await new Promise((resolve) => window.setTimeout(resolve, 700));
  return {
    purchaseToken: sandboxToken(userId, productId),
    productId,
    orderId: `GPA.TEST-${Date.now()}`,
    platform: "sandbox",
  };
}
