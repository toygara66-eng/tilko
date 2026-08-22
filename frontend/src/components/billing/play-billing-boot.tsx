"use client";

import { useEffect } from "react";
import { installPlayBillingBridge } from "@/lib/billing";

/** Android WebView’de Play Billing köprüsünü erken bağlar. */
export function PlayBillingBoot() {
  useEffect(() => {
    installPlayBillingBridge();
    const id = window.setInterval(() => installPlayBillingBridge(), 1500);
    window.setTimeout(() => window.clearInterval(id), 12_000);
    return () => window.clearInterval(id);
  }, []);
  return null;
}
