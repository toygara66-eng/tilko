"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";
import { useProfile } from "@/components/profile/profile-context";
import { isSignedIn } from "@/lib/auth";
import { hardNavigate, normalizeAppPath } from "@/lib/path";

const OPEN = new Set([
  "/hedef",
  "/admin",
  "/giris",
  "/hoca",
  "/gizlilik",
  "/hakkinda",
  "/hesap-sil",
]);

export function ExamTargetGate() {
  const { profile, ready } = useProfile();
  const path = normalizeAppPath(usePathname());

  useEffect(() => {
    if (!ready) return;
    if (!isSignedIn()) return;
    if (profile.role === "teacher" || profile.role === "admin") return;
    // Sunucu veya yerel: hedef seçildiyse /hedef’e zorlama (flash önlemi).
    if (profile.isOnboarded || Boolean(profile.examTarget?.trim())) return;
    if (OPEN.has(path)) return;
    hardNavigate("/hedef");
  }, [
    ready,
    profile.isOnboarded,
    profile.examTarget,
    profile.role,
    path,
  ]);

  return null;
}
