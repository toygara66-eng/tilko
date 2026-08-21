"use client";

import { useState } from "react";
import { Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PlayCheckoutModal } from "@/components/billing/play-checkout-modal";

export function ProUpgradeButton({
  className,
  size = "lg",
  label = "Tilko Pro'ya geç",
}: {
  className?: string;
  size?: "default" | "lg" | "sm";
  label?: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button type="button" size={size} className={className} onClick={() => setOpen(true)}>
        <Sparkles className="h-4 w-4" />
        {label}
      </Button>
      <PlayCheckoutModal open={open} onClose={() => setOpen(false)} />
    </>
  );
}
