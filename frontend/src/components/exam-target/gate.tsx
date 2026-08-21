"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useProfile } from "@/components/profile/profile-context";

const OPEN = new Set(["/hedef", "/admin", "/giris", "/hoca"]);

export function ExamTargetGate() {
  const { profile, ready } = useProfile();
  const path = usePathname();
  const router = useRouter();

  useEffect(() => {
    if (!ready) return;
    if (profile.role === "teacher" || profile.role === "admin") return;
    if (profile.isOnboarded) return;
    if (OPEN.has(path)) return;
    router.replace("/hedef");
  }, [ready, profile.isOnboarded, profile.role, path, router]);

  return null;
}
