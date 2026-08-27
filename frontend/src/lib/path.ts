/** next.config trailingSlash:true → pathname çoğu zaman `/gizlilik/` gelir. */
export function normalizeAppPath(path: string | null | undefined): string {
  if (!path) return "/";
  let value = path;
  // Capacitor / static export ilk yüklemede /index.html gelebiliyor
  if (value.endsWith("/index.html")) {
    value = value.slice(0, -"/index.html".length) || "/";
  } else if (value.endsWith("index.html")) {
    value = value.slice(0, -"index.html".length) || "/";
  } else if (value.endsWith(".html")) {
    value = value.slice(0, -".html".length);
  }
  if (value.length > 1 && value.endsWith("/")) {
    value = value.slice(0, -1);
  }
  return value || "/";
}

export function isNativeApp(): boolean {
  if (typeof window === "undefined") return false;
  const cap = (
    window as unknown as {
      Capacitor?: { isNativePlatform?: () => boolean };
    }
  ).Capacitor;
  try {
    return Boolean(cap?.isNativePlatform?.());
  } catch {
    return false;
  }
}

/**
 * Capacitor WebView'de `/giris/` bazen 404/takılıyor.
 * Native'de her zaman origin + .../index.html kullan.
 */
export function hardNavigate(path: string) {
  if (typeof window === "undefined") return;
  let target = path.startsWith("/") ? path : `/${path}`;
  if (target !== "/" && !target.endsWith("/")) {
    target = `${target}/`;
  }

  const current = normalizeAppPath(window.location.pathname);
  if (current === normalizeAppPath(target)) {
    // Aynı path'teyiz ama yine de index.html'e zorla (Cap dizin URL'si bozuk olabilir)
    if (!isNativeApp()) return;
  }

  const origin = window.location.origin || "https://localhost";
  let href: string;
  if (isNativeApp() || origin.includes("localhost")) {
    href =
      target === "/"
        ? `${origin}/index.html`
        : `${origin}${target}index.html`;
  } else {
    href = `${origin}${target}`;
  }

  try {
    window.location.href = href;
  } catch {
    window.location.assign(href);
  }
}
