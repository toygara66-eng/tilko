"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { QuizFlow } from "@/components/diagnostic/quiz-flow";
import {
  getDiagnosticExam,
  submitCheckup,
  type CheckupReport,
  type DiagnosticQuestion,
} from "@/lib/api";
import { getUserId } from "@/lib/user";
import { useProfile } from "@/components/profile/profile-context";

const SNOOZE_KEY = "tilko_checkup_snooze";

function snoozed(): boolean {
  if (typeof window === "undefined") return false;
  const raw = window.localStorage.getItem(SNOOZE_KEY);
  if (!raw) return false;
  return Date.now() < Number(raw);
}

function snooze() {
  window.localStorage.setItem(SNOOZE_KEY, String(Date.now() + 20 * 60 * 60 * 1000));
}

export function CheckupCard() {
  const { profile, refresh } = useProfile();
  const [open, setOpen] = useState(false);
  const [questions, setQuestions] = useState<DiagnosticQuestion[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [report, setReport] = useState<CheckupReport | null>(null);

  useEffect(() => {
    if (!profile.isTested || !profile.checkupDue || snoozed()) return;
    setOpen(true);
    getDiagnosticExam(getUserId(), "checkup")
      .then((data) => setQuestions(data.questions))
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Check-up yüklenemedi"),
      );
  }, [profile.isTested, profile.checkupDue]);

  if (!open) return null;

  function dismiss() {
    snooze();
    setOpen(false);
  }

  async function finish(answers: { question_id: string; chosen: string }[]) {
    setBusy(true);
    setError("");
    try {
      const data = await submitCheckup(getUserId(), answers);
      setReport(data);
      void refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Check-up gönderilemedi");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="glow-orange relative overflow-hidden rounded-2xl border-2 border-orange-400/70 bg-white/60 p-5 backdrop-blur-xl dark:bg-zinc-950/50">
      <button
        type="button"
        onClick={dismiss}
        className="absolute right-3 top-3 rounded-full p-1 text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200"
        aria-label="Sonra"
      >
        <X className="h-4 w-4" />
      </button>
      <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-orange-600 dark:text-orange-300">
        Haftalık Check-up 🦊
      </p>
      <h2 className="mt-1 text-lg font-semibold text-zinc-900 dark:text-white">
        Hey {profile.title}, nabız zamanı.
      </h2>
      {report ? (
        <div className="mt-3 space-y-3">
          <p className="text-sm leading-relaxed text-zinc-800 dark:text-zinc-100">
            {report.improvement_summary}
          </p>
          <p className="font-mono text-orange-600 dark:text-orange-300">
            {Math.round(report.score)}
            {report.score_delta != null
              ? ` · ${report.score_delta > 0 ? "+" : ""}${report.score_delta}`
              : null}
          </p>
          <Button type="button" onClick={dismiss} className="h-10">
            Tamam
          </Button>
        </div>
      ) : questions.length ? (
        <div className="mt-3">
          <p className="mb-3 text-sm text-zinc-500">5 soru. Sıkılmazsın.</p>
          {error ? <p className="mb-2 text-sm text-red-500">{error}</p> : null}
          <QuizFlow questions={questions} busy={busy} onComplete={finish} />
        </div>
      ) : (
        <p className="mt-3 text-sm text-zinc-500">{error || "Hazırlanıyor…"}</p>
      )}
      {!report ? (
        <button
          type="button"
          onClick={dismiss}
          className="mt-3 text-xs text-zinc-400 hover:text-orange-500"
        >
          Sonra
        </button>
      ) : (
        <Link href="/profil" className="mt-2 inline-block text-xs text-orange-600">
          Grafiğe bak
        </Link>
      )}
    </section>
  );
}
