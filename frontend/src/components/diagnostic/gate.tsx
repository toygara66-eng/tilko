"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";
import { useProfile } from "@/components/profile/profile-context";
import { isSignedIn } from "@/lib/auth";
import { hardNavigate, normalizeAppPath } from "@/lib/path";

const OPEN = new Set([
  "/teshis",
  "/hedef",
  "/admin",
  "/giris",
  "/hoca",
  "/gizlilik",
  "/hakkinda",
  "/hesap-sil",
]);

export function DiagnosticGate() {
  const { profile, ready } = useProfile();
  const path = normalizeAppPath(usePathname());

  useEffect(() => {
    if (!ready) return;
    if (!isSignedIn()) return;
    if (profile.role === "teacher" || profile.role === "admin") return;
    if (!profile.isOnboarded && !profile.examTarget?.trim()) return;
    // Teşhis bir kez bittiyse tekrar /teshis açma.
    if (profile.isTested) return;
    if (OPEN.has(path)) return;
    hardNavigate("/teshis");
  }, [
    ready,
    profile.isOnboarded,
    profile.examTarget,
    profile.isTested,
    profile.role,
    path,
  ]);

  return null;
}
