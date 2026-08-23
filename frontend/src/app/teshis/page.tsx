"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Loader2 } from "lucide-react";
import { QuizFlow } from "@/components/diagnostic/quiz-flow";
import { Button } from "@/components/ui/button";
import {
  getDiagnosticExam,
  submitDiagnostic,
  humanizeNetworkError,
  type DiagnosticQuestion,
  type DiagnosticReport,
} from "@/lib/api";
import { getUserId } from "@/lib/user";
import { useProfile } from "@/components/profile/profile-context";
import { useRouter } from "next/navigation";

export default function TeshisPage() {
  const router = useRouter();
  const { profile, refresh, apply } = useProfile();
  const [questions, setQuestions] = useState<DiagnosticQuestion[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [report, setReport] = useState<DiagnosticReport | null>(null);

  useEffect(() => {
    getDiagnosticExam(getUserId(), "baseline")
      .then((data) => setQuestions(data.questions))
      .catch((err) =>
        setError(humanizeNetworkError(err, "Sınav yüklenemedi")),
      );
  }, []);

  useEffect(() => {
    if (profile.isOnboarded && profile.isTested && !report) {
      router.replace("/");
    }
  }, [profile.isOnboarded, profile.isTested, report, router]);

  async function finish(answers: { question_id: string; chosen: string }[]) {
    setBusy(true);
    setError("");
    try {
      const data = await submitDiagnostic(getUserId(), answers);
      setReport(data);
      apply({
        isTested: true,
        weakTopics: data.weak_topics,
        baselineScore: data.score,
        analysisSummary: data.analysis_summary,
        recommendedVideos: data.recommended_videos,
        checkupDue: false,
      });
      void refresh();
    } catch (err) {
      setError(humanizeNetworkError(err, "Analiz gönderilemedi"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto w-full max-w-lg">
      <section className="glow-orange relative overflow-hidden rounded-2xl border-2 border-orange-400/80 bg-white/55 p-6 backdrop-blur-xl dark:bg-zinc-950/45">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,_rgba(251,146,60,0.22),transparent_55%)]" />
        <div className="relative space-y-5">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-orange-600 dark:text-orange-300">
              Tilko Seviye Teşhisi
            </p>
            <h1 className="mt-1 text-2xl font-semibold tracking-tight text-zinc-900 dark:text-white">
              Önce nabzını ölçelim, {profile.title}.
            </h1>
            <p className="mt-2 text-sm text-zinc-500">
              8 soru. Ana sayfaya buradan geçersin.
            </p>
          </div>
          {error ? (
            <div className="space-y-3">
              <p className="text-sm text-red-500">{error}</p>
              <Button
                type="button"
                className="h-12 w-full"
                onClick={() => {
                  apply({ isTested: true });
                  router.replace("/");
                }}
              >
                Av’a geç
              </Button>
            </div>
          ) : null}
          {report ? (
            <div className="space-y-4">
              <p className="text-base leading-relaxed text-zinc-800 dark:text-zinc-100">
                {typeof report.analysis_summary === "string"
                  ? report.analysis_summary
                  : "Analiz tamamlandı."}
              </p>
              <p className="font-mono text-3xl text-orange-600 dark:text-orange-300">
                {Math.round(report.score)}
                <span className="ml-2 text-sm text-zinc-500">
                  net {report.net_range}
                </span>
              </p>
              {report.weak_topics.length ? (
                <p className="text-sm text-zinc-500">
                  Odak: {report.weak_topics.join(", ")}
                </p>
              ) : null}
              {report.recommended_videos.length ? (
                <div className="space-y-2">
                  <p className="text-[11px] uppercase tracking-[0.2em] text-zinc-500">
                    Önerilen dersler
                  </p>
                  {report.recommended_videos.map((video) => (
                    <a
                      key={video.url}
                      href={video.url}
                      target="_blank"
                      rel="noreferrer"
                      className="block rounded-xl border border-orange-400/30 bg-orange-500/5 px-3 py-2 text-sm text-orange-800 dark:text-orange-200"
                    >
                      {video.topic} · {video.title}
                    </a>
                  ))}
                </div>
              ) : null}
              <Button asChild className="h-12 w-full">
                <Link href="/" onClick={() => apply({ isTested: true })}>
                  Av’a geç
                </Link>
              </Button>
            </div>
          ) : questions.length ? (
            <QuizFlow questions={questions} busy={busy} onComplete={finish} />
          ) : (
            <p className="flex items-center gap-2 text-sm text-zinc-500">
              <Loader2 className="h-4 w-4 animate-spin" />
            </p>
          )}
        </div>
      </section>
    </div>
  );
}
