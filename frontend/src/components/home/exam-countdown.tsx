"use client";

import Link from "next/link";
import { useProfile } from "@/components/profile/profile-context";

function turkishDate(iso: string, fallback = "") {
  if (fallback) return fallback;
  if (!iso) return "";
  return new Date(`${iso.slice(0, 10)}T12:00:00`).toLocaleDateString("tr-TR", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

export function ExamCountdown() {
  const { profile } = useProfile();
  if (!profile.examLabel && !profile.examTarget) return null;
  const headline =
    profile.countdownHeadline ||
    (profile.daysUntilExam >= 0
      ? `${profile.examLabel || "Sınav"} · ${profile.daysUntilExam} gün`
      : `${profile.examLabel || "Sınav"} geride`);
  const todayLabel = turkishDate(profile.today, profile.todayLabel);
  const examLabel = turkishDate(profile.examDate, profile.examDateLabel);

  return (
    <section className="glow-orange relative overflow-hidden rounded-3xl border-2 border-orange-400/80 bg-white/55 px-5 py-6 text-center backdrop-blur-xl dark:bg-zinc-950/50">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_center,_rgba(249,115,22,0.28),transparent_62%)]" />
      {todayLabel ? (
        <p className="relative text-[11px] font-medium text-zinc-500">
          Bugün · {todayLabel}
        </p>
      ) : null}
      <p className="relative mt-2 text-[11px] font-semibold uppercase tracking-[0.32em] text-orange-600 dark:text-orange-300">
        {profile.examLabel || "Hedef sınav"}
      </p>
      <h1 className="relative mt-2 text-3xl font-semibold tracking-tight text-orange-500 drop-shadow-[0_0_22px_rgba(249,115,22,0.55)] md:text-4xl">
        {headline}
      </h1>
      {examLabel ? (
        <p className="relative mt-2 text-sm text-zinc-600 dark:text-zinc-300">
          Sınav · {examLabel}
        </p>
      ) : null}
      <Link
        href="/hedef?degistir=1"
        className="relative mt-3 inline-block text-[11px] text-orange-600/80 hover:underline dark:text-orange-300/80"
      >
        Hedefi değiştir
      </Link>
    </section>
  );
}
