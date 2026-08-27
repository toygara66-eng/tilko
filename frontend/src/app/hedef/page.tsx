"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useProfile } from "@/components/profile/profile-context";
import { setExamTarget } from "@/lib/api";
import { EXAM_OPTIONS, familyOf, type ExamTargetId } from "@/lib/exams";
import { getUserId } from "@/lib/user";
import { hardNavigate } from "@/lib/path";
import { cn } from "@/lib/utils";

export default function HedefPage() {
  return (
    <Suspense
      fallback={
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-zinc-100 dark:bg-zinc-950">
          <Loader2 className="h-6 w-6 animate-spin text-orange-500" />
        </div>
      }
    >
      <HedefForm />
    </Suspense>
  );
}

function HedefForm() {
  const search = useSearchParams();
  const changing = search.get("degistir") === "1";
  const { profile, ready, apply, refresh } = useProfile();
  const [picked, setPicked] = useState<ExamTargetId | "">("");
  const [family, setFamily] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [welcome, setWelcome] = useState("");

  useEffect(() => {
    if (!ready || welcome || changing) return;
    // Yerel cache ile sunucu yarışını önle: hem bayrak hem hedef dolu olsun.
    const done = profile.isOnboarded && Boolean(profile.examTarget?.trim());
    if (!done) return;
    hardNavigate(profile.isTested ? "/" : "/teshis");
  }, [
    ready,
    profile.isOnboarded,
    profile.examTarget,
    profile.isTested,
    welcome,
    changing,
  ]);

  function chooseFamily(id: string) {
    setFamily(id);
    setError("");
    const group = EXAM_OPTIONS.find((item) => item.id === id);
    if (!group) return;
    if (group.children.length === 1) {
      setPicked(group.children[0].id as ExamTargetId);
      return;
    }
    if (id === "kpss") {
      setPicked("kpss_lisans");
      return;
    }
    setPicked(group.children[0].id as ExamTargetId);
  }

  async function continueOnboarding() {
    if (!picked) {
      setError("Önce hedef sınavını seç.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const data = await setExamTarget(getUserId(), picked);
      apply({
        isOnboarded: true,
        isTested: Boolean(data.is_tested),
        examTarget: data.exam_target,
        examLabel: data.exam_label,
        title: data.title || profile.title,
        daysUntilExam: data.days_left ?? profile.daysUntilExam,
        examDate: data.exam_date || profile.examDate,
        examDateLabel: data.exam_date_label || profile.examDateLabel,
        today: data.today || profile.today,
        todayLabel: data.today_label || profile.todayLabel,
        countdownHeadline: data.headline || "",
        weakTopics: data.reset ? [] : profile.weakTopics,
        analysisSummary: data.reset ? "" : profile.analysisSummary,
        recommendedVideos: data.reset ? [] : profile.recommendedVideos,
      });
      setWelcome(data.message);
      void refresh();
      window.setTimeout(() => {
        hardNavigate(data.reset || !data.is_tested ? "/teshis" : "/");
      }, 1600);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Hedef kaydedilemedi");
    } finally {
      setBusy(false);
    }
  }

  if (!ready) {
    return (
      <div className="fixed inset-0 z-40 flex items-center justify-center bg-zinc-100 dark:bg-zinc-950">
        <Loader2 className="h-6 w-6 animate-spin text-orange-500" />
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-zinc-100 px-4 dark:bg-zinc-950">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top,_rgba(249,115,22,0.22),transparent_55%)] dark:bg-[radial-gradient(ellipse_at_top,_rgba(249,115,22,0.18),transparent_50%)]" />
      <section className="glow-orange relative w-full max-w-lg overflow-hidden rounded-3xl border-2 border-orange-400/80 bg-white/55 p-6 shadow-[0_0_40px_rgba(249,115,22,0.18)] backdrop-blur-xl dark:bg-zinc-950/50">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,_rgba(251,146,60,0.28),transparent_55%)]" />
        <div className="relative space-y-5">
          {welcome ? (
            <div className="space-y-3 py-8 text-center">
              <p className="text-4xl">{profile.titleEmoji || "🦊"}</p>
              <h1 className="text-2xl font-semibold tracking-tight text-zinc-900 dark:text-white">
                {welcome}
              </h1>
              <p className="text-sm text-zinc-500">Rota çiziliyor…</p>
            </div>
          ) : (
            <>
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-orange-600 dark:text-orange-300">
                  Sınav Hedefi Onboarding
                </p>
                <h1 className="mt-1 text-2xl font-semibold tracking-tight text-zinc-900 dark:text-white">
                  Hedef Sınavını Seç 🎯
                </h1>
                <p className="mt-2 text-sm text-zinc-500">
                  Koç, Sazan Avı ve tuzak analizleri bu seçime göre şekillenir,{" "}
                  {profile.title}.
                </p>
              </div>
              <div className="grid gap-2">
                {EXAM_OPTIONS.map((item) => {
                  const active = family === item.id || familyOf(picked) === item.id;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => chooseFamily(item.id)}
                      className={cn(
                        "rounded-2xl border px-4 py-3 text-left transition backdrop-blur-md",
                        active
                          ? "border-orange-400 bg-orange-500/15 shadow-[0_0_18px_rgba(249,115,22,0.25)]"
                          : "border-zinc-200/80 bg-white/40 hover:border-orange-300/70 dark:border-zinc-800 dark:bg-zinc-900/40",
                      )}
                    >
                      <p className="text-sm font-semibold text-zinc-900 dark:text-white">
                        {item.emoji} {item.title}
                      </p>
                      <p className="mt-0.5 text-xs text-zinc-500">{item.hint}</p>
                    </button>
                  );
                })}
              </div>
              {family && (EXAM_OPTIONS.find((item) => item.id === family)?.children.length ?? 0) > 1 ? (
                <div className="flex flex-wrap gap-2">
                  {EXAM_OPTIONS.find((item) => item.id === family)?.children.map((child) => (
                    <button
                      key={child.id}
                      type="button"
                      onClick={() => setPicked(child.id as ExamTargetId)}
                      className={cn(
                        "rounded-full border px-3 py-1.5 text-xs font-medium transition",
                        picked === child.id
                          ? "border-orange-400 bg-orange-500 text-zinc-950"
                          : "border-orange-400/40 bg-orange-500/10 text-orange-800 dark:text-orange-200",
                      )}
                    >
                      {child.label}
                    </button>
                  ))}
                </div>
              ) : null}
              {error ? <p className="text-sm text-red-500">{error}</p> : null}
              <Button
                className="h-12 w-full"
                disabled={busy || !picked}
                onClick={() => void continueOnboarding()}
              >
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Devam Et"}
              </Button>
            </>
          )}
        </div>
      </section>
    </div>
  );
}
