"use client";

import { useEffect } from "react";
import { usePenalty } from "@/components/pomodoro/penalty-context";
import { useProfile } from "@/components/profile/profile-context";
import { HocaNote } from "@/components/notes/human-note-card";
import { Button } from "@/components/ui/button";

export function PenaltyLock() {
  const { isPenalized, streak, needed, trap, message, busy, submitAnswer } =
    usePenalty();
  const { profile } = useProfile();

  useEffect(() => {
    if (!isPenalized) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") event.preventDefault();
    };
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = "";
      window.removeEventListener("keydown", onKey);
    };
  }, [isPenalized]);

  if (!isPenalized) return null;

  const ratio = needed === 0 ? 0 : streak / needed;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="penalty-title"
      className="fixed inset-0 z-[9999] flex items-center justify-center bg-zinc-950/95 p-4"
    >
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,_rgba(239,68,68,0.18),transparent_55%)]" />
      <div className="relative w-full max-w-xl rounded-2xl border border-red-500/40 bg-zinc-900 p-6 shadow-[0_0_40px_rgba(239,68,68,0.25)]">
        <p className="text-xs font-semibold uppercase tracking-[0.25em] text-red-400">
          Acımasız Pomodoro
        </p>
        <h2
          id="penalty-title"
          className="mt-2 text-3xl font-semibold tracking-tight text-red-300 md:text-4xl"
        >
          Hey {profile.title}, odaklanmayı bozma!
        </h2>
        <p className="mt-2 text-sm text-zinc-400">
          Sekme değişti, tarayıcı alta alındı. Kilidi açmak için Tuzak
          Defteri&apos;nden peş peşe {needed} doğru.
        </p>

        <div className="mt-5 h-2 overflow-hidden rounded-full bg-zinc-800">
          <div
            className="h-full rounded-full bg-cyan-400 transition-all duration-300"
            style={{ width: `${Math.min(ratio, 1) * 100}%` }}
          />
        </div>
        <p className="mt-2 text-sm text-cyan-300">
          Seri {streak}/{needed}
        </p>

        {trap ? (
          <div
            className="protect-copy mt-5 space-y-3"
            onCopy={(event) => event.preventDefault()}
            onContextMenu={(event) => event.preventDefault()}
          >
            {trap.topic ? (
              <p className="text-xs uppercase tracking-widest text-zinc-500">
                {trap.topic}
              </p>
            ) : null}
            <p className="text-base text-zinc-100">{trap.question_text}</p>
            <div className="grid gap-2">
              {Object.entries(trap.options || {}).map(([letter, text]) => (
                <Button
                  key={letter}
                  variant="outline"
                  disabled={busy}
                  className="h-auto justify-start whitespace-normal py-3 text-left"
                  onClick={() => submitAnswer(letter)}
                >
                  <span className="text-cyan-400">{letter})</span> {text}
                </Button>
              ))}
            </div>
            {trap.teacher_note || trap.distractor_analysis ? (
              <HocaNote text={trap.teacher_note || trap.distractor_analysis} />
            ) : null}
          </div>
        ) : (
          <p className="mt-5 text-sm text-zinc-500">Soru yükleniyor…</p>
        )}

        {message ? (
          <p className="mt-4 text-sm text-red-300">{message}</p>
        ) : null}
      </div>
    </div>
  );
}
