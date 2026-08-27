"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";
import { useProfile } from "@/components/profile/profile-context";
import { getStoredRole } from "@/lib/auth";
import { hardNavigate, normalizeAppPath } from "@/lib/path";

const TEACHER_OPEN = new Set(["/hoca", "/giris", "/admin"]);

export function RoleGate() {
  const { profile, ready } = useProfile();
  const path = normalizeAppPath(usePathname());
  const role = (() => {
    const stored = getStoredRole();
    if (stored === "teacher" || stored === "admin") return stored;
    return profile.role || stored;
  })();

  useEffect(() => {
    if (!ready) return;
    if (role === "teacher" || role === "admin") {
      if (!TEACHER_OPEN.has(path)) hardNavigate("/hoca");
      return;
    }
    if (path === "/hoca") hardNavigate("/");
  }, [ready, role, path]);

  return null;
}
