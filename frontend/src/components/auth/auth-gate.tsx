"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { isSignedIn } from "@/lib/auth";
import { clearUserId } from "@/lib/user";
import { normalizeAppPath } from "@/lib/path";

/** Giriş/kayıt olmadan uygulama kullanılmaz. */
const PUBLIC = new Set(["/giris", "/admin", "/gizlilik"]);

export function AuthGate() {
  const path = normalizeAppPath(usePathname());
  const router = useRouter();

  useEffect(() => {
    if (PUBLIC.has(path)) return;
    if (isSignedIn()) return;
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
    router.replace("/giris");
  }, [path, router]);

  return null;
}
