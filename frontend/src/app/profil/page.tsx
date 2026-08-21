"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useProfile } from "@/components/profile/profile-context";
import { PrizeBadge } from "@/components/challenge/prize-badge";
import { ProgressChart } from "@/components/diagnostic/progress-chart";
import { MistakeDoctorCard } from "@/components/analytics/mistake-doctor-card";
import { FeedbackCard } from "@/components/feedback/feedback-form";
import { TargetScoreForm } from "@/components/profile/target-score-form";
import {
  getMistakeDoctor,
  getProgressHistory,
  type MistakeDoctorReport,
  type ProgressPoint,
} from "@/lib/api";
import { getUserId } from "@/lib/user";

export default function ProfilePage() {
  const { profile } = useProfile();
  const settled = profile.prize?.settled;
  const live = profile.prize?.live;
  const earned =
    settled?.is_free_next_month || (settled?.discount_percentage ?? 0) > 0;
  const projected = live?.badge && live.projected;
  const [points, setPoints] = useState<ProgressPoint[]>([]);
  const [doctor, setDoctor] = useState<MistakeDoctorReport | null>(null);
  const [doctorLoading, setDoctorLoading] = useState(true);

  useEffect(() => {
    getProgressHistory(getUserId())
      .then((data) => setPoints(data.points))
      .catch(() => setPoints([]));
  }, [profile.isTested]);

  useEffect(() => {
    setDoctorLoading(true);
    getMistakeDoctor(getUserId())
      .then(setDoctor)
      .catch(() => setDoctor(null))
      .finally(() => setDoctorLoading(false));
  }, [profile.xp]);

  return (
    <div className="mx-auto max-w-lg space-y-6">
      <div>
        <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-orange-600 dark:text-orange-300">
          Profil
        </p>
        <h1 className="mt-1 text-3xl font-semibold tracking-tight">
          {profile.titleEmoji} {profile.title}
        </h1>
        <p className="mt-1 text-sm text-zinc-500">
          {profile.xp} XP
          {profile.examLabel ? ` · ${profile.examLabel}` : ""}
          {" · "}
          <Link href="/hedef?degistir=1" className="text-orange-600 hover:underline dark:text-orange-300">
            hedefi değiştir
          </Link>
        </p>
      </div>

      {profile.analysisSummary ? (
        <section className="rounded-2xl border border-orange-400/40 bg-white/55 p-5 backdrop-blur-xl dark:bg-zinc-950/45">
          <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-orange-600 dark:text-orange-300">
            Seviye rotası
          </p>
          <p className="mt-2 text-sm leading-relaxed text-zinc-700 dark:text-zinc-300">
            {profile.analysisSummary}
          </p>
          {profile.weakTopics.length ? (
            <p className="mt-2 text-xs text-zinc-500">
              Odak: {profile.weakTopics.join(", ")}
            </p>
          ) : null}
        </section>
      ) : null}

      <TargetScoreForm />

      <section className="rounded-2xl border border-orange-400/40 bg-white/55 p-5 backdrop-blur-xl dark:bg-zinc-950/45">
        <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-orange-600 dark:text-orange-300">
          Abonelik
        </p>
        {profile.isPremium ? (
          <p className="mt-2 text-sm text-zinc-700 dark:text-zinc-300">
            Tilko Pro açık. Analiz kotası yok.
            {profile.subscriptionExpiresAt
              ? ` Bitiş: ${new Date(profile.subscriptionExpiresAt).toLocaleDateString("tr-TR")}`
              : ""}
          </p>
        ) : (
          <p className="mt-2 text-sm text-zinc-500">
            Ücretsiz katmandasın.{" "}
            <Link href="/pro" className="text-orange-600 dark:text-orange-300">
              Tilko Pro&apos;ya geç
            </Link>
          </p>
        )}
      </section>

      <MistakeDoctorCard report={doctor} loading={doctorLoading} />

      <section className="rounded-2xl border border-orange-400/40 bg-white/55 p-5 backdrop-blur-xl dark:bg-zinc-950/45">
        <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-orange-600 dark:text-orange-300">
          Gelişim grafiği
        </p>
        <div className="mt-3">
          <ProgressChart points={points} />
        </div>
      </section>

      <section className="glow-orange rounded-2xl border border-orange-400/50 bg-white/60 p-5 backdrop-blur-xl dark:bg-zinc-950/50">
        <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-orange-600 dark:text-orange-300">
          Aylık ödül
        </p>
        {earned ? (
          <div className="mt-3 space-y-2">
            <PrizeBadge
              label={settled?.badge || "Ödül"}
              className="text-xs"
            />
            <p className="text-sm text-zinc-700 dark:text-zinc-300">
              {settled?.is_free_next_month
                ? "Geçen ay ilk 3’e girdin. Bu ay TİLKO sende bedava."
                : `Geçen ay ${settled?.monthly_rank}. oldun. Bu ay %${settled?.discount_percentage} indirim senin.`}
            </p>
          </div>
        ) : projected ? (
          <div className="mt-3 space-y-2">
            <PrizeBadge label={live?.badge || ""} className="text-xs" />
            <p className="text-sm text-zinc-700 dark:text-zinc-300">
              Bu ay {live?.monthly_rank}. sıradasın. Ay sonunda bu dilim kilitlenir.
            </p>
          </div>
        ) : (
          <p className="mt-3 text-sm text-zinc-500">
            {profile.prize?.prize_banner ||
              "Kürsü Ödülü: Ay sonunda ilk 3'e girenler sonraki ay BEDAVA Pro kazanıyor!"}
          </p>
        )}
      </section>

      <FeedbackCard />

      <Link
        href="/"
        className="inline-block text-sm text-orange-600 dark:text-orange-300"
      >
        Av’a dön
      </Link>
    </div>
  );
}
