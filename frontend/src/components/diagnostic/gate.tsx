"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useProfile } from "@/components/profile/profile-context";

const OPEN = new Set(["/teshis", "/hedef", "/admin", "/giris", "/hoca"]);

export function DiagnosticGate() {
  const { profile, ready } = useProfile();
  const path = usePathname();
  const router = useRouter();

  useEffect(() => {
    if (!ready) return;
    if (profile.role === "teacher" || profile.role === "admin") return;
    if (!profile.isOnboarded) return;
    if (profile.isTested) return;
    if (OPEN.has(path)) return;
    router.replace("/teshis");
  }, [ready, profile.isOnboarded, profile.isTested, profile.role, path, router]);

  return null;
}
