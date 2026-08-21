"use client";

import { useEffect, useRef, useState } from "react";
import { Loader2, Timer } from "lucide-react";
import { formatMs } from "@/components/challenge/kurnaz-list";
import { Button } from "@/components/ui/button";
import { useProfile } from "@/components/profile/profile-context";
import {
  getDailyChallenge,
  startDailyChallenge,
  submitDailyChallenge,
  type DailyChallenge,
  type DailyChallengeResult,
} from "@/lib/api";
import { getDeviceId, getUserId } from "@/lib/user";
import { cn } from "@/lib/utils";
import { ReportQuestionControl } from "@/components/questions/report-question";
import { PremiseAnalyzer } from "@/components/questions/premise-analyzer";
import { SolutionSteps } from "@/components/questions/solution-steps";

export function DailyHuntCard() {
  const { apply, refresh, profile } = useProfile();
  const [challenge, setChallenge] = useState<DailyChallenge | null>(null);
  const [error, setError] = useState("");
  const [open, setOpen] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<DailyChallengeResult | null>(null);
  const startedAt = useRef<number | null>(null);
  const userId = useRef("");
  const startPromise = useRef<Promise<unknown> | null>(null);

  useEffect(() => {
    userId.current = getUserId();
    getDailyChallenge(userId.current)
      .then((data) => {
        setChallenge(data);
        if (data.result) {
          setResult(data.result);
          setOpen(true);
        }
      })
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Av yüklenemedi"),
      );
  }, []);

  useEffect(() => {
    if (!open || result || !startedAt.current) return;
    const id = window.setInterval(() => {
      if (startedAt.current) {
        setElapsed(Math.round(performance.now() - startedAt.current));
      }
    }, 32);
    return () => window.clearInterval(id);
  }, [open, result]);

  useEffect(() => {
    if (!open || result || !challenge) return;
    if (startPromise.current) return;
    startPromise.current = startDailyChallenge({
      user_id: userId.current || getUserId(),
      challenge_id: challenge.id,
      device_id: getDeviceId(),
    }).catch((err) => {
      setError(err instanceof Error ? err.message : "Av başlatılamadı");
    });
  }, [open, challenge, result]);

  function openHunt() {
    setOpen(true);
    if (!result && startedAt.current === null) {
      startedAt.current = performance.now();
      setElapsed(0);
    }
  }

  async function pick(letter: string) {
    if (!challenge || result || busy) return;
    setBusy(true);
    setError("");
    try {
      if (startPromise.current) await startPromise.current;
      const data = await submitDailyChallenge({
        user_id: userId.current || getUserId(),
        chosen: letter,
        challenge_id: challenge.id,
        device_id: getDeviceId(),
      });
      setResult(data);
      setElapsed(data.time_spent_ms);
      if (data.xp_gained) {
        apply({
          xp: data.xp,
          title: data.title,
          titleEmoji: data.title_emoji,
        });
      }
      void refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Cevap gönderilemedi");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section
      className={cn(
        "glow-orange relative overflow-hidden rounded-2xl border-2 border-orange-400/80 bg-white/55 p-6 backdrop-blur-xl dark:bg-zinc-950/45",
        !open && "cursor-pointer hover:border-orange-300",
      )}
      onClick={!open ? openHunt : undefined}
      role={!open ? "button" : undefined}
      tabIndex={!open ? 0 : undefined}
      onKeyDown={
        !open
          ? (event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                openHunt();
              }
            }
          : undefined
      }
    >
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,_rgba(251,146,60,0.22),transparent_55%)]" />
      <div className="relative space-y-5">
        <div className="flex items-start justify-between gap-3">
          <h2 className="text-2xl font-semibold tracking-tight text-zinc-900 dark:text-white">
            Günün Sazan Avı 🦊
          </h2>
          <div className="flex items-center gap-2">
            {open && challenge ? (
              <ReportQuestionControl questionId={`hunt:${challenge.id}`} />
            ) : null}
            {open && !result ? (
              <div className="flex items-center gap-2 font-mono text-sm text-orange-600 dark:text-orange-200">
                <Timer className="h-4 w-4" />
                {formatMs(elapsed)}
              </div>
            ) : null}
          </div>
        </div>

        {error ? <p className="text-sm text-red-500">{error}</p> : null}

        {!open ? (
          <p className="text-sm text-orange-700 dark:text-orange-300">Başla</p>
        ) : !challenge ? (
          <p className="flex items-center gap-2 text-sm text-zinc-500">
            <Loader2 className="h-4 w-4 animate-spin" />
          </p>
        ) : result ? (
          <ResultView result={result} title={profile.title} />
        ) : (
          <div
            className="protect-copy space-y-3"
            onCopy={(event) => event.preventDefault()}
            onContextMenu={(event) => event.preventDefault()}
          >
            <p className="text-base font-medium text-zinc-900 dark:text-zinc-100">
              {challenge.question_text}
            </p>
            <PremiseAnalyzer premises={challenge.premises} reveal={false} />
            <div className="grid gap-2">
              {Object.entries(challenge.options).map(([letter, text]) => (
                <Button
                  key={letter}
                  type="button"
                  variant="outline"
                  disabled={busy}
                  className="h-auto justify-start whitespace-normal border-orange-400/30 py-3 text-left hover:border-orange-400 hover:bg-orange-500/10"
                  onClick={(event) => {
                    event.stopPropagation();
                    pick(letter);
                  }}
                >
                  <span className="mr-2 font-mono text-orange-500">{letter})</span>
                  {text}
                </Button>
              ))}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

function ResultView({
  result,
  title,
}: {
  result: DailyChallengeResult;
  title: string;
}) {
  const [openSolution, setOpenSolution] = useState(false);
  const numerical = result.subject_type === "sayisal";
  const hasCoach =
    Boolean(result.step_by_step_solution?.length) || Boolean(result.shortcut_tactic);

  if (result.is_correct && (result.is_cheated || result.is_suspicious)) {
    return (
      <div className="space-y-1">
        <p className="text-sm font-medium text-amber-600 dark:text-amber-300">
          {result.suspicious_reason || "Şüpheli hız. Listeye yazılmadı."}
        </p>
        <p className="font-mono text-2xl text-zinc-500">
          {formatMs(result.time_spent_ms)}
        </p>
      </div>
    );
  }

  const body = !result.is_correct ? (
    <p className="font-scribble text-2xl leading-snug text-red-600 dark:text-red-300">
      {result.wrong_message || `Hey ${title}, sazan gibi atladın!`}
    </p>
  ) : (
    <div className="space-y-1">
      <p className="text-sm font-medium text-orange-600 dark:text-orange-300">
        Helal olsun {title}!
      </p>
      <p className="font-mono text-3xl text-orange-600 dark:text-orange-300">
        {formatMs(result.time_spent_ms)}
      </p>
      <p className="text-sm text-zinc-500">
        {result.rank ? `${result.rank}. sıra` : "Doğru"}
        {result.xp_gained ? ` · +${result.xp_gained} XP` : null}
      </p>
    </div>
  );

  return (
    <div className="space-y-4">
      {result.misconception_tag ? (
        <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-orange-600 dark:text-orange-300">
          {result.misconception_tag}
        </p>
      ) : null}
      {body}
      <PremiseAnalyzer premises={result.premises} reveal />
      {hasCoach ? (
        <div className="space-y-2">
          <button
            type="button"
            onClick={() => setOpenSolution((value) => !value)}
            className="text-xs font-semibold uppercase tracking-[0.16em] text-orange-600 dark:text-orange-300"
          >
            {openSolution || numerical ? "Adım adım çözüm" : "Çözümü aç"}
          </button>
          {(openSolution || numerical) ? (
            <SolutionSteps
              steps={result.step_by_step_solution}
              tactic={result.shortcut_tactic}
            />
          ) : null}
        </div>
      ) : result.trap_explanation ? (
        <p className="text-sm text-zinc-600 dark:text-zinc-400">{result.trap_explanation}</p>
      ) : null}
    </div>
  );
}
