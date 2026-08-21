export const PLAY_PACKAGE = "com.tilko.app";
export const PLAY_STORE_URL = `https://play.google.com/store/apps/details?id=${PLAY_PACKAGE}`;

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

type IntegrityBridge = {
  isOfficial?: () => boolean;
  fingerprints?: () => string;
  packageName?: () => string;
  openPlayStore?: () => void;
  ok?: boolean;
};

declare global {
  interface Window {
    TilkoIntegrity?: IntegrityBridge;
    Capacitor?: {
      isNativePlatform?: () => boolean;
      getPlatform?: () => string;
    };
  }
}

function previewTrap(): boolean {
  if (typeof window === "undefined") return false;
  const query = new URLSearchParams(window.location.search);
  return query.get("sazan") === "1" || query.get("tilko_trap") === "1";
}

function nativeAndroid(): boolean {
  if (typeof window === "undefined") return false;
  const cap = window.Capacitor;
  if (cap?.isNativePlatform?.() && cap.getPlatform?.() === "android") return true;
  return Boolean(window.TilkoIntegrity);
}

export function openOfficialPlayStore() {
  try {
    window.TilkoIntegrity?.openPlayStore?.();
    return;
  } catch {
    /* tarayıcı */
  }
  window.location.href = PLAY_STORE_URL;
}

export async function probeIntegrity(): Promise<"ok" | "pirate"> {
  if (typeof window === "undefined") return "ok";
  if (previewTrap()) return "pirate";

  if (nativeAndroid() && !window.TilkoIntegrity) {
    for (let i = 0; i < 10; i += 1) {
      await sleep(80);
      if (window.TilkoIntegrity) break;
    }
  }

  const bridge = window.TilkoIntegrity;
  if (!bridge) {
    return nativeAndroid() ? "pirate" : "ok";
  }

  try {
    const official =
      typeof bridge.isOfficial === "function" ? bridge.isOfficial() : Boolean(bridge.ok);
    return official ? "ok" : "pirate";
  } catch {
    return "pirate";
  }
}
