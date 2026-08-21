"use client";

import { useRef } from "react";
import { usePathname, useRouter } from "next/navigation";

const TAP_COUNT = 5;
const TAP_GAP_MS = 450;

export function useSecretAdminTap() {
  const router = useRouter();
  const path = usePathname();
  const taps = useRef({ count: 0, last: 0 });

  return (event: { preventDefault: () => void; stopPropagation: () => void }) => {
    const now = Date.now();
    const state = taps.current;
    if (now - state.last > TAP_GAP_MS) state.count = 0;
    state.last = now;
    state.count += 1;
    if (state.count < TAP_COUNT) return;
    event.preventDefault();
    event.stopPropagation();
    state.count = 0;
    if (path !== "/admin") router.push("/admin");
  };
}
