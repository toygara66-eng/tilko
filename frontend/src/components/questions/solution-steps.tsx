"use client";

import { useState } from "react";
import { ChevronDown, Lightbulb } from "lucide-react";
import { cn } from "@/lib/utils";

export function SolutionSteps({
  steps,
  tactic,
  className,
}: {
  steps?: string[];
  tactic?: string;
  className?: string;
}) {
  const items = (steps || []).filter((line) => line.trim());
  const shortcut = (tactic || "").trim();
  const [open, setOpen] = useState(0);

  if (!items.length && !shortcut) return null;

  return (
    <div className={cn("space-y-2", className)}>
      {items.map((step, index) => {
        const active = open === index;
        return (
          <button
            key={`${index}-${step.slice(0, 24)}`}
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              setOpen(active ? -1 : index);
            }}
            className={cn(
              "w-full rounded-2xl border px-4 py-3 text-left backdrop-blur-xl transition",
              "border-orange-400/35 bg-white/50 dark:bg-zinc-950/40",
              active && "border-orange-400/80 shadow-[0_0_24px_rgba(251,146,60,0.18)]",
            )}
          >
            <span className="flex items-center justify-between gap-3">
              <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-orange-600 dark:text-orange-300">
                Adım {index + 1}
              </span>
              <ChevronDown
                className={cn(
                  "h-4 w-4 text-orange-500 transition",
                  active && "rotate-180",
                )}
              />
            </span>
            {active ? (
              <p className="mt-2 text-sm leading-relaxed text-zinc-800 dark:text-zinc-100">
                {step}
              </p>
            ) : (
              <p className="mt-1 truncate text-sm text-zinc-500">{step}</p>
            )}
          </button>
        );
      })}
      {shortcut ? (
        <div className="rounded-2xl border border-orange-400/50 bg-orange-500/10 px-4 py-3 backdrop-blur-xl">
          <p className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-orange-600 dark:text-orange-300">
            <Lightbulb className="h-3.5 w-3.5" />
            Pratik Taktik
          </p>
          <p className="mt-2 text-sm leading-relaxed text-zinc-800 dark:text-zinc-100">
            {shortcut}
          </p>
        </div>
      ) : null}
    </div>
  );
}
