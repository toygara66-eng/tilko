"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { ChevronLeft, ChevronRight, Clock, Loader2, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PremiseAnalyzer } from "@/components/questions/premise-analyzer";
import { ReportQuestionControl } from "@/components/questions/report-question";
import { SolutionSteps } from "@/components/questions/solution-steps";
import { useProfile } from "@/components/profile/profile-context";
import { getUserId } from "@/lib/user";
import { cn } from "@/lib/utils";
import {
  generateDynamicExam,
  getDynamicExam,
  getDynamicExamCatalog,
  submitDynamicExam,
  type DynamicExamCatalog,
  type DynamicExamQuestion,
  type DynamicExamReport,
  type DynamicExamSession,
} from "@/lib/api";

const SESSION_KEY = "tilko_dynamic_exam_id";

type Phase = "setup" | "loading" | "taking" | "submitting" | "report";

function formatClock(total: number) {
  const safe = Math.max(0, total);
  const minutes = Math.floor(safe / 60);
  const seconds = safe % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function rememberExam(id: number) {
  try {
    window.sessionStorage.setItem(SESSION_KEY, String(id));
  } catch {
    /* ignore */
  }
}

function rememberedExam() {
  try {
    const raw = window.sessionStorage.getItem(SESSION_KEY);
    const id = Number(raw);
    return Number.isFinite(id) && id > 0 ? id : 0;
  } catch {
    return 0;
  }
}

function forgetExam() {
  try {
    window.sessionStorage.removeItem(SESSION_KEY);
  } catch {
    /* ignore */
  }
}

export function ExamLab() {
  const { profile, refresh } = useProfile();
  const [phase, setPhase] = useState<Phase>("setup");
  const [catalog, setCatalog] = useState<DynamicExamCatalog | null>(null);
  const [subjects, setSubjects] = useState<string[]>([]);
  const [count, setCount] = useState(10);
  const [session, setSession] = useState<DynamicExamSession | null>(null);
  const [index, setIndex] = useState(0);
  const [picks, setPicks] = useState<Record<string, string>>({});
  const [remaining, setRemaining] = useState(0);
  const [report, setReport] = useState<DynamicExamReport | null>(null);
  const [error, setError] = useState("");
  const startedAt = useRef(Date.now());
  const submitting = useRef(false);
  const picksRef = useRef<Record<string, string>>({});
  const sessionRef = useRef<DynamicExamSession | null>(null);

  useEffect(() => {
    getDynamicExamCatalog(getUserId(), profile.examTarget || undefined)
      .then((data) => {
        setCatalog(data);
        setSubjects(data.subjects.slice(0, Math.min(3, data.subjects.length)));
        setCount(data.question_counts[0] || 10);
      })
      .catch(() => {
        setCatalog({
          user_id: getUserId(),
          exam_target: profile.examTarget,
          exam_label: profile.examLabel,
          family: "",
          subjects: ["Tarih", "Vatandaşlık", "Coğrafya", "Türkçe"],
          question_counts: [10, 15, 20],
          seconds_per_question: 75,
        });
      });
  }, [profile.examTarget, profile.examLabel]);

  useEffect(() => {
    const examId = rememberedExam();
    if (!examId) return;
    getDynamicExam(getUserId(), examId)
      .then((data) => {
        if (data.status === "submitted" && data.report) {
          setReport(data.report);
          setPhase("report");
          forgetExam();
          return;
        }
        if (!data.questions.length) return;
        setSession(data);
        sessionRef.current = data;
        setRemaining(data.remaining_seconds || data.duration_seconds);
        startedAt.current = Date.now();
        setPhase("taking");
      })
      .catch(() => forgetExam());
  }, []);

  const questions = session?.questions || [];
  const current = questions[index];

  const finish = useCallback(
    async (exam: DynamicExamSession, nextPicks: Record<string, string>) => {
      if (submitting.current) return;
      submitting.current = true;
      setPhase("submitting");
      setError("");
      const answers = exam.questions.map((item) => ({
        question_id: item.id,
        chosen: nextPicks[item.id] || "",
      }));
      const spent = Math.max(
        1,
        Math.round((Date.now() - startedAt.current) / 1000),
      );
      try {
        const data = await submitDynamicExam({
          user_id: getUserId(),
          exam_id: exam.exam_id,
          answers,
          time_spent_seconds: spent,
        });
        setReport(data);
        setPhase("report");
        forgetExam();
        await refresh();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Karne üretilemedi");
        setPhase("taking");
      } finally {
        submitting.current = false;
      }
    },
    [refresh],
  );

  useEffect(() => {
    picksRef.current = picks;
  }, [picks]);

  useEffect(() => {
    sessionRef.current = session;
  }, [session]);

  useEffect(() => {
    if (phase !== "taking") return;
    const timer = window.setInterval(() => {
      setRemaining((value) => {
        if (value <= 1) {
          window.clearInterval(timer);
          const live = sessionRef.current;
          if (live) void finish(live, picksRef.current);
          return 0;
        }
        return value - 1;
      });
    }, 1000);
    return () => window.clearInterval(timer);
  }, [phase, finish]);

  useEffect(() => {
    if (phase !== "taking") return;
    function onLeave(event: BeforeUnloadEvent) {
      event.preventDefault();
      event.returnValue = "";
    }
    window.addEventListener("beforeunload", onLeave);
    return () => window.removeEventListener("beforeunload", onLeave);
  }, [phase]);

  async function start() {
    if (!subjects.length) {
      setError("En az bir ders seç.");
      return;
    }
    setError("");
    setPhase("loading");
    try {
      const data = await generateDynamicExam({
        user_id: getUserId(),
        exam_target: catalog?.exam_target || profile.examTarget,
        subjects,
        question_count: count,
      });
      rememberExam(data.exam_id);
      setSession(data);
      sessionRef.current = data;
      setPicks({});
      picksRef.current = {};
      setIndex(0);
      setRemaining(data.remaining_seconds || data.duration_seconds);
      startedAt.current = Date.now();
      setPhase("taking");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Deneme üretilemedi. Biraz sonra dene.",
      );
      setPhase("setup");
    }
  }

  function toggleSubject(name: string) {
    setSubjects((current) =>
      current.includes(name)
        ? current.filter((item) => item !== name)
        : [...current, name],
    );
  }

  const answered = useMemo(
    () => questions.filter((item) => picks[item.id]).length,
    [questions, picks],
  );

  if (phase === "report" && report) {
    return <ExamReportCard report={report} onReset={() => {
      setReport(null);
      setSession(null);
      setPicks({});
      setPhase("setup");
    }} />;
  }

  if (phase === "taking" || phase === "submitting") {
    if (!current || !session) {
      return (
        <p className="flex items-center gap-2 text-sm text-zinc-500">
          <Loader2 className="h-4 w-4 animate-spin" />
          Sınav hazırlanıyor
        </p>
      );
    }
    return (
      <ExamRunner
        questions={questions}
        current={current}
        index={index}
        picks={picks}
        remaining={remaining}
        answered={answered}
        busy={phase === "submitting"}
        error={error}
        onIndex={setIndex}
        onPick={(letter) =>
          setPicks((prev) => ({ ...prev, [current.id]: letter }))
        }
        onFinish={() => void finish(session, picks)}
      />
    );
  }

  const subjectList = catalog?.subjects || [];
  const counts = catalog?.question_counts || [10, 15, 20];

  return (
    <section className="protect-copy space-y-5 rounded-3xl border border-orange-400/45 bg-white/60 p-5 shadow-[0_0_40px_rgba(251,146,60,0.16)] backdrop-blur-xl dark:bg-zinc-950/50">
      <div>
        <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-orange-600 dark:text-orange-300">
          Yapay Zeka Deneme Laboratuvarı
        </p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight text-zinc-900 dark:text-white">
          ÖSYM DNA’sıyla anlık deneme 📝
        </h1>
        <p className="mt-2 text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">
          {catalog?.exam_label || profile.examLabel || "Hedef sınavın"} üslubu,
          arşiv kökleri ve Tuzak Defteri zayıflıkların harmanlanır. Süre sayacı
          açık, karne koç üslubunda gelir.
        </p>
      </div>

      <div>
        <p className="mb-2 text-xs font-medium text-zinc-500">Dersler</p>
        <div className="flex flex-wrap gap-2">
          {subjectList.map((name) => {
            const on = subjects.includes(name);
            return (
              <button
                key={name}
                type="button"
                onClick={() => toggleSubject(name)}
                className={cn(
                  "rounded-full border px-3 py-1.5 text-sm transition",
                  on
                    ? "border-orange-400 bg-orange-500 text-zinc-950 shadow-[0_0_16px_rgba(251,146,60,0.4)]"
                    : "border-zinc-300 bg-white/40 text-zinc-600 hover:border-orange-400/60 dark:border-zinc-700 dark:bg-zinc-900/50 dark:text-zinc-300",
                )}
              >
                {name}
              </button>
            );
          })}
        </div>
      </div>

      <div>
        <p className="mb-2 text-xs font-medium text-zinc-500">Soru sayısı</p>
        <div className="flex flex-wrap gap-2">
          {counts.map((value) => (
            <button
              key={value}
              type="button"
              onClick={() => setCount(value)}
              className={cn(
                "min-w-14 rounded-full border px-3 py-1.5 text-sm font-semibold transition",
                count === value
                  ? "border-orange-400 bg-orange-500/20 text-orange-700 dark:text-orange-200"
                  : "border-zinc-300 text-zinc-500 hover:border-orange-400/50 dark:border-zinc-700",
              )}
            >
              {value}
            </button>
          ))}
        </div>
        <p className="mt-2 text-xs text-zinc-500">
          Süre yaklaşık {Math.round((count * (catalog?.seconds_per_question || 75)) / 60)}{" "}
          dakika. Üretim 30–90 saniye sürebilir.
        </p>
      </div>

      {error ? <p className="text-sm text-red-500">{error}</p> : null}

      <Button
        type="button"
        size="lg"
        disabled={phase === "loading" || !subjects.length}
        onClick={() => void start()}
        className="h-12 w-full bg-orange-500 text-zinc-950 shadow-[0_0_22px_rgba(251,146,60,0.45)] hover:bg-orange-400"
      >
        {phase === "loading" ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" />
            ÖSYM DNA harmanlanıyor
          </>
        ) : (
          <>
            <Sparkles className="h-4 w-4" />
            Denemeyi Başlat
          </>
        )}
      </Button>
    </section>
  );
}

function ExamRunner({
  questions,
  current,
  index,
  picks,
  remaining,
  answered,
  busy,
  error,
  onIndex,
  onPick,
  onFinish,
}: {
  questions: DynamicExamQuestion[];
  current: DynamicExamQuestion;
  index: number;
  picks: Record<string, string>;
  remaining: number;
  answered: number;
  busy: boolean;
  error: string;
  onIndex: (value: number) => void;
  onPick: (letter: string) => void;
  onFinish: () => void;
}) {
  const chosen = picks[current.id] || "";
  const last = index === questions.length - 1;
  const urgent = remaining < 60;

  return (
    <div
      className="protect-copy space-y-5"
      onCopy={(event) => event.preventDefault()}
      onContextMenu={(event) => event.preventDefault()}
    >
      <header className="flex items-center justify-between gap-3 rounded-2xl border border-orange-400/40 bg-white/55 px-4 py-3 backdrop-blur-xl dark:bg-zinc-950/50">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-orange-600 dark:text-orange-300">
            Deneme
          </p>
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            {index + 1} / {questions.length} · {current.topic}
          </p>
        </div>
        <div
          className={cn(
            "flex items-center gap-2 font-mono text-lg font-semibold",
            urgent
              ? "text-red-500"
              : "text-orange-600 dark:text-orange-300",
          )}
        >
          <Clock className="h-4 w-4" />
          {formatClock(remaining)}
        </div>
      </header>

      <div className="h-1.5 overflow-hidden rounded-full bg-zinc-200/80 dark:bg-zinc-800">
        <div
          className="h-full rounded-full bg-orange-500 shadow-[0_0_12px_rgba(251,146,60,0.7)] transition-all"
          style={{ width: `${((index + 1) / questions.length) * 100}%` }}
        />
      </div>

      <div className="flex flex-wrap gap-1.5">
        {questions.map((item, i) => {
          const marked = Boolean(picks[item.id]);
          return (
            <button
              key={item.id}
              type="button"
              disabled={busy}
              onClick={() => onIndex(i)}
              className={cn(
                "h-8 w-8 rounded-lg text-xs font-semibold transition",
                i === index
                  ? "bg-orange-500 text-zinc-950 shadow-[0_0_12px_rgba(251,146,60,0.45)]"
                  : marked
                    ? "border border-orange-400/50 bg-orange-500/15 text-orange-700 dark:text-orange-200"
                    : "border border-zinc-300 text-zinc-500 dark:border-zinc-700",
              )}
            >
              {i + 1}
            </button>
          );
        })}
      </div>

      <section className="rounded-3xl border border-orange-400/30 bg-white/55 p-5 backdrop-blur-xl dark:bg-zinc-950/45">
        <div className="flex items-start justify-between gap-3">
          <p className="text-lg font-medium leading-snug text-zinc-900 dark:text-white">
            {current.question_text}
          </p>
          <ReportQuestionControl questionId={current.id} className="shrink-0" />
        </div>
        <PremiseAnalyzer premises={current.premises} />
        <div className="mt-4 grid gap-2">
          {Object.entries(current.options).map(([letter, text]) => (
            <Button
              key={letter}
              type="button"
              variant="outline"
              disabled={busy}
              className={cn(
                "h-auto justify-start whitespace-normal border-orange-400/25 py-3 text-left hover:border-orange-400 hover:bg-orange-500/10",
                chosen === letter && "border-orange-400 bg-orange-500/15",
              )}
              onClick={() => onPick(letter)}
            >
              <span className="mr-2 font-mono text-orange-500">{letter})</span>
              {text}
            </Button>
          ))}
        </div>
      </section>

      {error ? <p className="text-sm text-red-500">{error}</p> : null}

      <div className="flex items-center gap-2">
        <Button
          type="button"
          variant="outline"
          disabled={busy || index === 0}
          onClick={() => onIndex(index - 1)}
          className="border-orange-400/30"
        >
          <ChevronLeft className="h-4 w-4" />
          Önceki
        </Button>
        {!last ? (
          <Button
            type="button"
            disabled={busy}
            onClick={() => onIndex(index + 1)}
            className="flex-1 bg-orange-500 text-zinc-950 hover:bg-orange-400"
          >
            Sonraki
            <ChevronRight className="h-4 w-4" />
          </Button>
        ) : null}
        <Button
          type="button"
          disabled={busy}
          onClick={onFinish}
          className={cn(
            last
              ? "flex-1 bg-orange-500 text-zinc-950 hover:bg-orange-400"
              : "border-orange-400/40",
          )}
          variant={last ? "default" : "outline"}
        >
            {busy ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Karne yazılıyor
              </>
            ) : (
              `Sınavı bitir (${answered}/${questions.length})`
            )}
        </Button>
      </div>
    </div>
  );
}

function ExamReportCard({
  report,
  onReset,
}: {
  report: DynamicExamReport;
  onReset: () => void;
}) {
  return (
    <section className="space-y-5 rounded-3xl border border-orange-400/45 bg-white/60 p-5 shadow-[0_0_40px_rgba(251,146,60,0.16)] backdrop-blur-xl dark:bg-zinc-950/50">
      <div>
        <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-orange-600 dark:text-orange-300">
          Deneme karnesi
        </p>
        <h1 className="mt-1 text-2xl font-semibold text-zinc-900 dark:text-white">
          {report.title || "Koç"} bakıyor
        </h1>
      </div>
      <p className="font-mono text-4xl text-orange-600 dark:text-orange-300">
        {Math.round(report.score)}
        <span className="ml-2 text-sm text-zinc-500">
          {report.correct_count}/{report.total} · net {report.net_range}
        </span>
      </p>
      {report.xp_gained ? (
        <p className="text-sm text-zinc-500">+{report.xp_gained} XP</p>
      ) : null}
      {report.is_cheated ? (
        <p className="text-sm text-amber-600 dark:text-amber-400">
          Tempo şüphesi: süre çok kısaydı. Karneni yine de kaydettik.
        </p>
      ) : null}
      <p className="text-base leading-relaxed text-zinc-800 dark:text-zinc-100">
        {report.coach_summary}
      </p>
      <div className="rounded-2xl border border-orange-400/25 bg-orange-500/5 p-4">
        <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-orange-600 dark:text-orange-300">
          Zayıflık analizi
        </p>
        <p className="mt-2 text-sm leading-relaxed text-zinc-700 dark:text-zinc-200">
          {report.weakness_analysis}
        </p>
        <p className="mt-3 text-sm text-zinc-600 dark:text-zinc-400">
          {report.prescription}
        </p>
      </div>
      {report.weak_topics.length || report.strong_topics.length ? (
        <div className="flex flex-wrap gap-2 text-xs">
          {report.strong_topics.map((topic) => (
            <span
              key={`s-${topic}`}
              className="rounded-full border border-emerald-400/40 bg-emerald-500/10 px-2.5 py-1 text-emerald-700 dark:text-emerald-300"
            >
              Kale: {topic}
            </span>
          ))}
          {report.weak_topics.map((topic) => (
            <span
              key={`w-${topic}`}
              className="rounded-full border border-orange-400/40 bg-orange-500/10 px-2.5 py-1 text-orange-800 dark:text-orange-200"
            >
              Açık: {topic}
            </span>
          ))}
        </div>
      ) : null}
      {Object.keys(report.topic_breakdown || {}).length ? (
        <div className="space-y-2">
          {Object.entries(report.topic_breakdown).map(([topic, row]) => (
            <div key={topic}>
              <div className="mb-1 flex justify-between text-xs text-zinc-500">
                <span>{topic}</span>
                <span>
                  {row.correct}/{row.total}
                </span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800">
                <div
                  className="h-full rounded-full bg-orange-500"
                  style={{ width: `${Math.round((row.ratio || 0) * 100)}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      ) : null}
      {report.traps_saved ? (
        <p className="text-xs text-zinc-500">
          {report.traps_saved} yanlış Tuzak Defteri’ne düştü.
        </p>
      ) : null}

      <div className="space-y-3">
        <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
          Soru çözümleri
        </p>
        {report.reviews.map((item, index) => (
          <article
            key={item.question_id}
            className={cn(
              "rounded-2xl border p-4",
              item.is_correct
                ? "border-emerald-400/30 bg-emerald-500/5"
                : "border-orange-400/30 bg-orange-500/5",
            )}
          >
            <p className="text-xs text-zinc-500">
              {index + 1}. {item.topic} · sen {item.chosen || "—"} · doğru {item.correct}
            </p>
            <p className="mt-1 text-sm font-medium text-zinc-900 dark:text-white">
              {item.question_text}
            </p>
            <PremiseAnalyzer premises={item.premises} reveal />
            {item.explanation ? (
              <p className="mt-2 text-sm leading-relaxed text-zinc-600 dark:text-zinc-300">
                {item.explanation}
              </p>
            ) : null}
            <SolutionSteps
              steps={item.step_by_step_solution}
              tactic={item.shortcut_tactic}
              className="mt-3"
            />
          </article>
        ))}
      </div>

      <div className="flex gap-2">
        <Button
          type="button"
          onClick={onReset}
          className="flex-1 bg-orange-500 text-zinc-950 hover:bg-orange-400"
        >
          Yeni deneme
        </Button>
        <Button asChild variant="outline" className="flex-1 border-orange-400/40">
          <Link href="/">Ana sayfa</Link>
        </Button>
      </div>
    </section>
  );
}
