const TOKEN_KEY = "tilko_jwt";
const SECRET_KEY = "tilko_auth_secret";
const ROLE_KEY = "tilko_role";
const MODE_KEY = "tilko_auth_mode";

function randomSecret() {
  const bytes = new Uint8Array(24);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (item) => item.toString(16).padStart(2, "0")).join("");
}

export function getAuthSecret(): string {
  if (typeof window === "undefined") return "local-dev-secret-tilko";
  const existing = window.localStorage.getItem(SECRET_KEY);
  if (existing && existing.length >= 8) return existing;
  const created = randomSecret();
  window.localStorage.setItem(SECRET_KEY, created);
  return created;
}

export function setAuthSecret(password: string) {
  if (typeof window === "undefined") return;
  if (password.length < 8) return;
  window.localStorage.setItem(SECRET_KEY, password);
  window.localStorage.setItem(MODE_KEY, "password");
}

export function setAuthMode(mode: "password" | "google") {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(MODE_KEY, mode);
  if (mode === "google") {
    window.localStorage.removeItem(SECRET_KEY);
  }
}

export function getAuthMode(): "password" | "google" {
  if (typeof window === "undefined") return "password";
  return window.localStorage.getItem(MODE_KEY) === "google" ? "google" : "password";
}

export function getStoredRole(): string {
  if (typeof window === "undefined") return "student";
  return window.localStorage.getItem(ROLE_KEY) || "student";
}

export function setStoredRole(role: string) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(ROLE_KEY, role || "student");
}

export function getToken(): string {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem(TOKEN_KEY) || "";
}

export function setToken(token: string) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function tokenValid(token: string): boolean {
  if (!token || token.split(".").length < 2) return false;
  try {
    const payload = JSON.parse(
      atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")),
    ) as { exp?: number };
    return (payload.exp || 0) * 1000 > Date.now() + 15_000;
  } catch {
    return false;
  }
}

let inflight: Promise<string> | null = null;

export async function ensureAuth(
  apiBase: string,
  userId: string,
): Promise<string> {
  const current = getToken();
  if (tokenValid(current)) return current;
  if (getAuthMode() === "google") {
    if (typeof window !== "undefined" && !window.location.pathname.startsWith("/giris")) {
      window.location.assign("/giris");
    }
    throw new Error("Google oturumu doldu. Tekrar giriş yap.");
  }
  if (inflight) return inflight;
  inflight = (async () => {
    const password = getAuthSecret();
    const body = JSON.stringify({ user_id: userId, password });
    const headers = { "Content-Type": "application/json" };
    const login = await fetch(`${apiBase}/auth/login`, {
      method: "POST",
      headers,
      body,
      signal: AbortSignal.timeout(90_000),
    });
    if (login.ok) {
      const data = (await login.json()) as { access_token: string };
      setToken(data.access_token);
      return data.access_token;
    }
    const register = await fetch(`${apiBase}/auth/register`, {
      method: "POST",
      headers,
      body,
      signal: AbortSignal.timeout(90_000),
    });
    if (!register.ok) {
      const err = (await register.json().catch(() => ({}))) as { detail?: unknown };
      const detail =
        typeof err.detail === "string"
          ? err.detail
          : Array.isArray(err.detail)
            ? "Kayıt bilgileri geçersiz."
            : "";
      throw new Error(detail || "Oturum açılamadı");
    }
    const data = (await register.json()) as { access_token: string };
    setToken(data.access_token);
    return data.access_token;
  })().finally(() => {
    inflight = null;
  });
  return inflight;
}

export function logout() {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(SECRET_KEY);
  window.localStorage.removeItem(ROLE_KEY);
  window.localStorage.removeItem(MODE_KEY);
  window.localStorage.removeItem("kpss_user_id");
  window.localStorage.removeItem("tilko_profile_flags");
  window.localStorage.removeItem("tilko_last_analyze");
  window.localStorage.removeItem("tilko_notebook_bump");
}

export function isAuthPublic(path: string) {
  return (
    path.startsWith("/auth/") ||
    path === "/login" ||
    path.startsWith("/health")
  );
}
