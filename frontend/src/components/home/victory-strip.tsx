"use client";

import { useProfile } from "@/components/profile/profile-context";

export function VictoryStrip() {
  const { profile } = useProfile();
  const label =
    profile.countdownHeadline ||
    (profile.daysUntilExam > 1
      ? `Zafere kalan · ${profile.daysUntilExam} gün`
      : profile.daysUntilExam === 1
        ? "Zafere kalan · 1 gün"
        : profile.daysUntilExam === 0
          ? "Zafer günü"
          : "Sınav geride");

  return (
    <div className="relative h-6 overflow-hidden">
      <div className="absolute inset-0 bg-gradient-to-r from-orange-600 via-amber-300 to-orange-500" />
      <p className="relative flex h-full items-center justify-center truncate px-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-zinc-950 sm:tracking-[0.28em]">
        {label}
      </p>
    </div>
  );
}
