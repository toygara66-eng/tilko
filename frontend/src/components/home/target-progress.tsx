"use client";

import Link from "next/link";
import { useProfile } from "@/components/profile/profile-context";
import { cn } from "@/lib/utils";

function daysLabel(days: number) {
  if (days > 1) return `${days} gün`;
  if (days === 1) return "1 gün";
  if (days === 0) return "bugün";
  return "sınav geride";
}

export function TargetProgress() {
  const { profile } = useProfile();
  const pct = Math.min(100, Math.max(0, profile.progressPct));
  const current = Math.round(profile.currentScore);
  const target = Math.round(profile.targetScore);
  const days = profile.daysUntilExam;

  return (
    <section className="space-y-2 px-0.5">
      <div className="flex items-baseline justify-between gap-3 text-[11px] text-zinc-500">
        <p>
          {days >= 0 ? (
            <>
              Sınava <span className="font-medium text-zinc-700 dark:text-zinc-300">{daysLabel(days)}</span>
            </>
          ) : (
            "Sınav geride"
          )}
        </p>
        <p className="tabular-nums">
          <span className="text-zinc-700 dark:text-zinc-300">{current}</span>
          <span className="mx-1 text-zinc-400">/</span>
          <span className="text-orange-600 dark:text-orange-300">{target}</span>
          {!profile.targetIsSet ? (
            <Link href="/profil" className="ml-1.5 text-[10px] text-orange-500/80 hover:underline">
              hedef
            </Link>
          ) : null}
        </p>
      </div>
      <div
        className="h-1 overflow-hidden rounded-full bg-zinc-200/80 dark:bg-zinc-800"
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Hedef puana ilerleme"
      >
        <div
          className={cn(
            "h-full rounded-full bg-orange-500 transition-[width] duration-700",
            "shadow-[0_0_10px_rgba(249,115,22,0.65)]",
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
    </section>
  );
}
