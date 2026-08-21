"use client";

import { useEffect, useState } from "react";
import { DailyHuntCard } from "@/components/challenge/daily-hunt";
import { PomodoroTimer } from "@/components/pomodoro/pomodoro-timer";
import { CheckupCard } from "@/components/diagnostic/checkup-card";
import { ProgressChart } from "@/components/diagnostic/progress-chart";
import { FoxMotto } from "@/components/home/fox-motto";
import { TargetProgress } from "@/components/home/target-progress";
import { ExamLabCard } from "@/components/exam/lab-card";
import { ExamCountdown } from "@/components/home/exam-countdown";
import { TeacherAssignmentCard } from "@/components/home/teacher-assignment-card";
import { getProgressHistory, type ProgressPoint } from "@/lib/api";
import { getUserId } from "@/lib/user";
import { useProfile } from "@/components/profile/profile-context";
import { cn } from "@/lib/utils";

type Stage = "hunt" | "focus";

export function HomeStage() {
  const { profile } = useProfile();
  const [stage, setStage] = useState<Stage>("hunt");
  const [points, setPoints] = useState<ProgressPoint[]>([]);

  useEffect(() => {
    if (!profile.isTested) return;
    getProgressHistory(getUserId())
      .then((data) => setPoints(data.points))
      .catch(() => setPoints([]));
  }, [profile.isTested, profile.checkupDue]);

  return (
    <div className="mx-auto w-full max-w-lg space-y-5">
      <ExamCountdown />
      <TeacherAssignmentCard />
      {profile.checkupDue ? <CheckupCard /> : null}
      <div className="space-y-3">
        <FoxMotto />
        <TargetProgress />
        <ExamLabCard />
      </div>
      <div className="mx-auto flex w-fit rounded-full border border-zinc-200/80 bg-white/60 p-1 backdrop-blur-md dark:border-zinc-800 dark:bg-zinc-900/50">
        {(
          [
            ["hunt", "Sazan Avı"],
            ["focus", "Pomodoro"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            onClick={() => setStage(id)}
            className={cn(
              "rounded-full px-4 py-1.5 text-sm font-medium transition",
              stage === id
                ? "bg-orange-500 text-zinc-950 shadow-[0_0_16px_rgba(251,146,60,0.45)]"
                : "text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200",
            )}
          >
            {label}
          </button>
        ))}
      </div>

      {stage === "hunt" ? <DailyHuntCard /> : <PomodoroTimer hero />}

      {points.length ? (
        <section className="rounded-2xl border border-orange-400/40 bg-white/50 p-4 backdrop-blur-xl dark:bg-zinc-950/40">
          <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-orange-600 dark:text-orange-300">
            Gelişim
          </p>
          <ProgressChart points={points} />
        </section>
      ) : null}
    </div>
  );
}
