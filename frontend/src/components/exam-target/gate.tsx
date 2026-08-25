"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useProfile } from "@/components/profile/profile-context";
import { isSignedIn } from "@/lib/auth";
import { normalizeAppPath } from "@/lib/path";

const OPEN = new Set(["/hedef", "/admin", "/giris", "/hoca", "/gizlilik", "/hakkinda"]);

export function ExamTargetGate() {
  const { profile, ready } = useProfile();
  const path = normalizeAppPath(usePathname());
  const router = useRouter();

  useEffect(() => {
    if (!ready) return;
    if (!isSignedIn()) return;
    if (profile.role === "teacher" || profile.role === "admin") return;
    // Yerel veya sunucu: bir kez seçildiyse bir daha /hedef zorlama.
    if (profile.isOnboarded) return;
    if (OPEN.has(path)) return;
    router.replace("/hedef");
  }, [ready, profile.isOnboarded, profile.role, path, router]);

  return null;
}
