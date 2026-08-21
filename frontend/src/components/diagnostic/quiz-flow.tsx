"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { DiagnosticQuestion } from "@/lib/api";
import { cn } from "@/lib/utils";
import { ReportQuestionControl } from "@/components/questions/report-question";

export function QuizFlow({
  questions,
  busy,
  onComplete,
}: {
  questions: DiagnosticQuestion[];
  busy?: boolean;
  onComplete: (answers: { question_id: string; chosen: string }[]) => void;
}) {
  const [index, setIndex] = useState(0);
  const [picks, setPicks] = useState<Record<string, string>>({});
  const current = questions[index];
  const chosen = current ? picks[current.id] : "";
  const last = index === questions.length - 1;

  if (!current) return null;

  function select(letter: string) {
    if (!current || busy) return;
    const next = { ...picks, [current.id]: letter };
    setPicks(next);
    if (!last) {
      window.setTimeout(() => setIndex((value) => value + 1), 160);
      return;
    }
    const answers = questions
      .map((item) => ({
        question_id: item.id,
        chosen: (next[item.id] || "").trim().slice(0, 1),
      }))
      .filter((item) => item.question_id && item.chosen);
    if (answers.length < questions.length) return;
    onComplete(answers);
  }

  return (
    <div
      className="protect-copy space-y-5"
      onCopy={(event) => event.preventDefault()}
      onContextMenu={(event) => event.preventDefault()}
    >
      <div className="flex items-center justify-between text-xs text-orange-700 dark:text-orange-300">
        <span>
          {index + 1} / {questions.length}
        </span>
        <span>{current.topic}</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-zinc-200/80 dark:bg-zinc-800">
        <div
          className="h-full rounded-full bg-orange-500 shadow-[0_0_12px_rgba(251,146,60,0.7)] transition-all"
          style={{ width: `${((index + (chosen ? 1 : 0)) / questions.length) * 100}%` }}
        />
      </div>
      <div className="flex items-start justify-between gap-3">
        <p className="text-lg font-medium leading-snug text-zinc-900 dark:text-white">
          {current.question_text}
        </p>
        <ReportQuestionControl questionId={current.id} className="shrink-0" />
      </div>
      <div className="grid gap-2">
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
            onClick={() => select(letter)}
          >
            <span className="mr-2 font-mono text-orange-500">{letter})</span>
            {typeof text === "string" ? text : ""}
          </Button>
        ))}
      </div>
      {busy ? (
        <p className="flex items-center gap-2 text-sm text-zinc-500">
          <Loader2 className="h-4 w-4 animate-spin" />
          Rota çiziliyor
        </p>
      ) : null}
    </div>
  );
}
