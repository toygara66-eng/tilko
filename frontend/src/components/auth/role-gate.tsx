"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useProfile } from "@/components/profile/profile-context";
import { getStoredRole } from "@/lib/auth";

const TEACHER_OPEN = new Set(["/hoca", "/giris", "/admin"]);

export function RoleGate() {
  const { profile, ready } = useProfile();
  const path = usePathname();
  const router = useRouter();
  const role = (() => {
    const stored = getStoredRole();
    if (stored === "teacher" || stored === "admin") return stored;
    return profile.role || stored;
  })();

  useEffect(() => {
    if (!ready) return;
    if (role === "teacher" || role === "admin") {
      if (!TEACHER_OPEN.has(path)) router.replace("/hoca");
      return;
    }
    if (path === "/hoca") router.replace("/");
  }, [ready, role, path, router]);

  return null;
}
