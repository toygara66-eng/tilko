"use client";

import { useEffect, useState, type ReactNode } from "react";
import { PirateTrap } from "@/components/security/pirate-trap";
import { probeIntegrity } from "@/lib/integrity";

export function IntegrityGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<"ok" | "pirate">("ok");

  useEffect(() => {
    let alive = true;
    probeIntegrity()
      .then((result) => {
        if (alive && result === "pirate") setState("pirate");
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, []);

  if (state === "pirate") {
    return <PirateTrap />;
  }

  return <>{children}</>;
}
