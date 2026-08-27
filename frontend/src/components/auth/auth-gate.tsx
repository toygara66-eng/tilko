"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { isSignedIn } from "@/lib/auth";
import { clearUserId } from "@/lib/user";
import { hardNavigate, normalizeAppPath } from "@/lib/path";

/** Giriş/kayıt olmadan uygulama kullanılmaz. */
const PUBLIC = new Set(["/giris", "/admin", "/gizlilik", "/hakkinda", "/hesap-sil"]);

export function AuthGate() {
  const path = normalizeAppPath(usePathname());
  const [allowed, setAllowed] = useState(() => {
    if (typeof window === "undefined") return true;
    return PUBLIC.has(path) || isSignedIn();
  });

  useEffect(() => {
    if (PUBLIC.has(path)) {
      setAllowed(true);
      return;
    }
    if (isSignedIn()) {
      setAllowed(true);
      return;
    }
    // Eski misafir (aday-*) kimliğini temizle
    try {
      const uid = window.localStorage.getItem("kpss_user_id") || "";
      if (!uid || uid === "local" || uid.startsWith("aday-")) {
        clearUserId();
        if (uid.startsWith("aday-")) {
          window.localStorage.removeItem("tilko_jwt");
          window.localStorage.removeItem("tilko_auth_secret");
          window.localStorage.removeItem("tilko_auth_mode");
        }
      }
    } catch {
      /* ignore */
    }
    setAllowed(false);
    hardNavigate("/giris");
  }, [path]);

  // Ana içeriği girişsiz göstermemek için shell bu bayrağı okur
  useEffect(() => {
    try {
      window.dispatchEvent(
        new CustomEvent("tilko-auth-gate", { detail: { allowed } }),
      );
    } catch {
      /* ignore */
    }
  }, [allowed]);

  return null;
}

export function useAuthAllowed(path: string): boolean {
  const normalized = normalizeAppPath(path);
  if (PUBLIC.has(normalized)) return true;
  if (typeof window === "undefined") return true;
  return isSignedIn();
}

export function isAuthPublicPath(path: string): boolean {
  return PUBLIC.has(normalizeAppPath(path));
}
