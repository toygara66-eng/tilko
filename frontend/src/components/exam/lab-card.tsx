"use client";

import Link from "next/link";
import { FlaskConical, Sparkles } from "lucide-react";

export function ExamLabCard() {
  return (
    <Link
      href="/deneme"
      className="block rounded-2xl border border-orange-400/50 bg-white/55 p-4 shadow-[0_0_28px_rgba(251,146,60,0.18)] backdrop-blur-xl transition hover:border-orange-400 hover:shadow-[0_0_36px_rgba(251,146,60,0.32)] dark:bg-zinc-950/45"
    >
      <div className="flex items-start gap-3">
        <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-orange-500 text-zinc-950 shadow-[0_0_18px_rgba(251,146,60,0.55)]">
          <FlaskConical className="h-5 w-5" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-orange-600 dark:text-orange-300">
            Laboratuvar
          </p>
          <h2 className="mt-1 text-base font-semibold text-zinc-900 dark:text-white">
            Yapay Zeka Deneme Laboratuvarı 📝
          </h2>
          <p className="mt-1 text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">
            ÖSYM DNA’sı ve Tuzak Defteri’ni harmanlayıp senin derslerinle anlık
            deneme üretir. Süre sayacı, koç karnesi.
          </p>
          <span className="mt-3 inline-flex items-center gap-1.5 text-sm font-semibold text-orange-600 dark:text-orange-300">
            <Sparkles className="h-4 w-4" />
            Denemeyi kur
          </span>
        </div>
      </div>
    </Link>
  );
}
