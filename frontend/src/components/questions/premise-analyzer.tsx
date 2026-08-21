"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import type { PremiseItem } from "@/lib/api";

export function PremiseAnalyzer({
  premises,
  reveal = false,
}: {
  premises?: PremiseItem[];
  reveal?: boolean;
}) {
  const items = (premises || []).filter((item) => item.text?.trim());
  const [openId, setOpenId] = useState<string | null>(null);

  if (!items.length) return null;

  return (
    <ul className="mt-3 space-y-2">
      {items.map((item) => {
        const open = openId === item.id;
        const showWhy = reveal && Boolean(item.why);
        return (
          <li key={item.id} className="relative">
            <button
              type="button"
              onClick={(event) => {
                event.stopPropagation();
                setOpenId(open ? null : item.id);
              }}
              onMouseEnter={() => showWhy && setOpenId(item.id)}
              onMouseLeave={() => setOpenId(null)}
              className={cn(
                "flex w-full items-start gap-3 rounded-2xl border px-3 py-2.5 text-left text-sm backdrop-blur-xl transition",
                "border-zinc-200/80 bg-white/45 hover:border-orange-400/50 dark:border-zinc-800 dark:bg-zinc-950/35",
                reveal && item.is_correct && "border-emerald-400/40",
                reveal && !item.is_correct && item.why && "border-red-400/35",
              )}
            >
              <span className="mt-0.5 font-mono text-xs font-semibold text-orange-500">
                {item.id}
              </span>
              <span className="text-zinc-800 dark:text-zinc-100">{item.text}</span>
            </button>
            {open && showWhy ? (
              <div className="absolute left-8 top-full z-20 mt-1 max-w-sm rounded-2xl border border-orange-400/40 bg-zinc-950/95 px-3 py-2 text-xs leading-relaxed text-zinc-100 shadow-[0_12px_40px_rgba(0,0,0,0.35)] backdrop-blur-xl">
                <p className="mb-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-orange-300">
                  {item.is_correct ? "Doğru öncül" : "ÖSYM çeldiricisi"}
                </p>
                <p>{item.why}</p>
              </div>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}
