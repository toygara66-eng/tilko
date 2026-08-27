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

/** Capacitor WebView'de App Router replace bazen takılıyor; sert yönlendir. */
export function hardNavigate(path: string) {
  if (typeof window === "undefined") return;
  const target = path.startsWith("/") ? path : `/${path}`;
  const withSlash =
    target === "/" ? "/" : target.endsWith("/") ? target : `${target}/`;
  try {
    const current = normalizeAppPath(window.location.pathname);
    if (current === normalizeAppPath(withSlash)) return;
  } catch {
    /* ignore */
  }
  window.location.assign(withSlash);
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
