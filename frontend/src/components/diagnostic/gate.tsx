"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useProfile } from "@/components/profile/profile-context";
import { isSignedIn } from "@/lib/auth";
import { normalizeAppPath } from "@/lib/path";

const OPEN = new Set(["/teshis", "/hedef", "/admin", "/giris", "/hoca", "/gizlilik"]);

export function DiagnosticGate() {
  const { profile, ready } = useProfile();
  const path = normalizeAppPath(usePathname());
  const router = useRouter();

  useEffect(() => {
    if (!ready) return;
    if (!isSignedIn()) return;
    if (profile.role === "teacher" || profile.role === "admin") return;
    if (!profile.isOnboarded) return;
    // Teşhis bir kez bittiyse (yerel/IP) tekrar /teshis açma.
    if (profile.isTested) return;
    if (OPEN.has(path)) return;
    router.replace("/teshis");
  }, [ready, profile.isOnboarded, profile.isTested, profile.role, path, router]);

  return null;
}
