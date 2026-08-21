"use client";

import { cn } from "@/lib/utils";

export function PrizeBadge({
  label,
  className,
}: {
  label: string;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border border-orange-400/50 bg-orange-500/15 px-2 py-0.5 text-[10px] font-semibold tracking-tight text-orange-800 dark:text-orange-200",
        className,
      )}
    >
      {label}
    </span>
  );
}
