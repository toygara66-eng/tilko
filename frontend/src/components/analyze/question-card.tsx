"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { HumanNoteCard } from "@/components/notes/human-note-card";
import { PremiseAnalyzer } from "@/components/questions/premise-analyzer";
import { SolutionSteps } from "@/components/questions/solution-steps";
import { ReportQuestionControl } from "@/components/questions/report-question";
import { saveTrap, type QuestionItem, type TeacherPersona } from "@/lib/api";
import { getUserId } from "@/lib/user";

export function QuestionCard({
  question,
  persona,
}: {
  question: QuestionItem;
  persona?: TeacherPersona;
}) {
  const [picked, setPicked] = useState("");
  const [msg, setMsg] = useState("");
  const [hocaNote, setHocaNote] = useState(question.trap_explanation || "");
  const started = useState(() => Date.now())[0];

  async function pick(letter: string) {
    setPicked(letter);
    const ok = letter === question.correct;
    if (ok) {
      setMsg("Doğru.");
      return;
    }
    const spent = Math.round((Date.now() - started) / 1000);
    try {
      const res = await saveTrap({
        user_id: getUserId(),
        question_text: question.text,
        chosen: letter,
        correct: question.correct,
        explanation: question.explanation,
        trap_explanation: question.trap_explanation,
        teacher_persona: persona,
        topic: question.topic,
        question_id: question.id,
        options: question.options,
        time_spent_seconds: spent,
        subject_type: question.subject_type,
        shortcut_tactic: question.shortcut_tactic,
        step_by_step_solution: question.step_by_step_solution,
        premises: question.premises,
        misconception_tag: question.misconception_tag,
        fen_branch: question.fen_branch,
        is_yks_fen_question: question.is_yks_fen_question,
      });
      setMsg(res.warning || "Tuzak defterine eklendi.");
      setHocaNote(res.trap?.teacher_note || question.trap_explanation);
    } catch {
      setMsg("Kayıt başarısız.");
      setHocaNote(question.trap_explanation || question.explanation);
    }
  }

  const wrong = picked && picked !== question.correct;

  return (
    <div
      className="protect-copy space-y-3"
      onCopy={(event) => event.preventDefault()}
      onContextMenu={(event) => event.preventDefault()}
    >
      <Card className="relative p-5">
        <ReportQuestionControl
          questionId={question.id}
          className="absolute right-3 top-3"
        />
        <div className="mb-3 flex flex-wrap gap-2 pr-16">
          {question.misconception_tag ? (
            <Badge className="border-orange-400/50 bg-orange-500/10 text-orange-700 dark:text-orange-200">
              {question.misconception_tag}
            </Badge>
          ) : null}
          {question.topic ? <Badge>{question.topic}</Badge> : null}
          {question.difficulty ? (
            <Badge className="border-zinc-300 bg-zinc-100 text-zinc-700 dark:border-zinc-700 dark:bg-zinc-800/80 dark:text-zinc-300">
              {question.difficulty}
            </Badge>
          ) : null}
        </div>
        <p className="text-sm text-zinc-800 dark:text-zinc-100">{question.text}</p>
        <PremiseAnalyzer premises={question.premises} reveal={Boolean(picked)} />
        <div className="mt-3 grid gap-2">
          {Object.entries(question.options).map(([letter, text]) => (
            <button
              key={letter}
              type="button"
              onClick={() => pick(letter)}
              className="rounded-xl border border-zinc-200 bg-zinc-50 px-3 py-2 text-left text-sm text-zinc-800 transition hover:border-cyan-500/50 dark:border-zinc-800 dark:bg-zinc-950/40 dark:text-zinc-300 dark:hover:border-cyan-400/40"
            >
              <span className="mr-2 text-cyan-400">{letter}</span>
              {text}
            </button>
          ))}
        </div>
      </Card>
      {wrong ? (
        <HumanNoteCard
          variant="trap"
          title={question.topic || "Tuzak analizi"}
          tilt={1.1}
          highlights={[picked, question.correct]}
          lines={[
            `ben -> ${picked}    doğru => ${question.correct}`,
            ...Object.entries(question.options).map(
              ([letter, text]) => `${letter}) ${text}`,
            ),
          ]}
          mnemonic={question.explanation}
          teacherNote={hocaNote}
          warning={msg || "Çeldiriciye gittin."}
        />
      ) : picked ? (
        <p className="font-scribble text-xl text-cyan-700 dark:text-cyan-300">
          Doğru — geç.
        </p>
      ) : null}
      {picked ? (
        <SolutionSteps
          steps={question.step_by_step_solution}
          tactic={question.shortcut_tactic}
        />
      ) : null}
    </div>
  );
}
