const PRODUCTION_API = "https://tilko-api.onrender.com";
const BAKED =
  (process.env.NEXT_PUBLIC_API_BASE || PRODUCTION_API).trim().replace(/\/$/, "");

function isLoopback(url: string): boolean {
  return /^https?:\/\/(127\.0\.0\.1|localhost|\[::1\])(:|\/|$)/i.test(url);
}

function isNativeCapacitor(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return Boolean(
      (
        window as unknown as {
          Capacitor?: { isNativePlatform?: () => boolean };
        }
      ).Capacitor?.isNativePlatform?.(),
    );
  } catch {
    return false;
  }
}

/**
 * Android APK build'inde .env.local (127.0.0.1) bazen gömülüyordu.
 * Native'de loopback cleartext yasak → her zaman canlı HTTPS.
 */
export function resolveApiBase(): string {
  let base = BAKED;
  if (typeof window !== "undefined") {
    try {
      const forced = window.localStorage.getItem("tilko_api_base")?.trim();
      if (forced) base = forced.replace(/\/$/, "");
    } catch {
      /* ignore */
    }
  }
  if (isLoopback(base) && (isNativeCapacitor() || process.env.NODE_ENV === "production")) {
    return PRODUCTION_API;
  }
  return base || PRODUCTION_API;
}

export function apiBaseLabel(): string {
  return resolveApiBase();
}
