"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { HumanNoteCard } from "@/components/notes/human-note-card";
import { NoteModeToggle } from "@/components/notes/note-mode";
import { QuestionCard } from "@/components/analyze/question-card";
import { fromNoteItem } from "@/lib/note-format";
import { listNotebook, type NotebookResponse } from "@/lib/api";
import { getUserId } from "@/lib/user";
import { subjectsFor } from "@/lib/exams";
import { useProfile } from "@/components/profile/profile-context";
import { cn } from "@/lib/utils";

const ALL = "Tümü";

export function MyNotes() {
  const { profile } = useProfile();
  const examSubjects = subjectsFor(profile.examTarget || "kpss_lisans");
  const [subject, setSubject] = useState(ALL);
  const [tab, setTab] = useState<"notes" | "questions">("notes");
  const [data, setData] = useState<NotebookResponse | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(true);

  const chips = useMemo(() => {
    const counts = new Map(
      (data?.subjects || []).map((item) => [item.name, item] as const),
    );
    const names = [
      ALL,
      ...examSubjects,
      ...(data?.subjects || [])
        .map((item) => item.name)
        .filter((name) => !examSubjects.includes(name)),
    ];
    return names.map((name) => {
      if (name === ALL) {
        const notes = (data?.subjects || []).reduce((sum, item) => sum + item.note_count, 0);
        const questions = (data?.subjects || []).reduce(
          (sum, item) => sum + item.question_count,
          0,
        );
        return { name, note_count: notes, question_count: questions };
      }
      return counts.get(name) || { name, note_count: 0, question_count: 0 };
    });
  }, [data, examSubjects]);

  useEffect(() => {
    let live = true;
    function load() {
      setBusy(true);
      listNotebook(getUserId(), subject === ALL ? undefined : subject)
        .then((payload) => {
          if (!live) return;
          setData(payload);
          setError("");
        })
        .catch((err) => {
          if (!live) return;
          setError(err instanceof Error ? err.message : "Notlar yüklenemedi");
        })
        .finally(() => {
          if (live) setBusy(false);
        });
    }
    load();
    const onBump = () => load();
    window.addEventListener("tilko-notebook-bump", onBump);
    window.addEventListener("storage", onBump);
    const onFocus = () => load();
    window.addEventListener("focus", onFocus);
    return () => {
      live = false;
      window.removeEventListener("tilko-notebook-bump", onBump);
      window.removeEventListener("storage", onBump);
      window.removeEventListener("focus", onFocus);
    };
  }, [subject]);

  const notes = data?.notes || [];
  const questions = data?.questions || [];
  const empty = !busy && notes.length === 0 && questions.length === 0;

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h1 className="font-scribble text-3xl text-amber-800 dark:text-amber-100 sm:text-4xl md:text-5xl">
            Notlarım
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-zinc-600 dark:text-zinc-400 sm:text-base">
            Analiz ettiğin videolardaki ders notları ve sorular burada birikir.
            Matematik, Türkçe, Tarih… derse bas, o güne kadar çıkanların hepsi gelsin.
          </p>
        </div>
        <NoteModeToggle className="self-start" />
      </div>

      <div className="flex flex-wrap gap-2">
        {chips.map((chip) => {
          const on = subject === chip.name;
          const total = chip.note_count + chip.question_count;
          return (
            <button
              key={chip.name}
              type="button"
              onClick={() => setSubject(chip.name)}
              className={cn(
                "rounded-full border px-3 py-1.5 text-sm transition",
                on
                  ? "border-orange-400 bg-orange-500 text-zinc-950 shadow-[0_0_16px_rgba(251,146,60,0.4)]"
                  : "border-zinc-300 bg-white/40 text-zinc-600 hover:border-orange-400/60 dark:border-zinc-700 dark:bg-zinc-900/50 dark:text-zinc-300",
              )}
            >
              {chip.name}
              {total ? (
                <span className={cn("ml-1 text-xs", on ? "text-zinc-800" : "text-zinc-400")}>
                  {chip.note_count}
                </span>
              ) : null}
            </button>
          );
        })}
      </div>

      <div className="flex gap-1">
        <button
          type="button"
          onClick={() => setTab("notes")}
          className={cn(
            "rounded-full px-3 py-1 text-xs font-medium",
            tab === "notes"
              ? "bg-orange-500 text-zinc-950"
              : "text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-800",
          )}
        >
          Notlar ({notes.length})
        </button>
        <button
          type="button"
          onClick={() => setTab("questions")}
          className={cn(
            "rounded-full px-3 py-1 text-xs font-medium",
            tab === "questions"
              ? "bg-orange-500 text-zinc-950"
              : "text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-800",
          )}
        >
          Sorular ({questions.length})
        </button>
      </div>

      {error ? <p className="text-sm text-red-400">{error}</p> : null}
      {busy ? <p className="text-sm text-zinc-500">Notlar yükleniyor…</p> : null}

      {empty ? (
        <HumanNoteCard
          title="Bu ders henüz boş"
          tilt={-0.6}
          lines={[
            "-> Analiz’den bir video çevir",
            "=> notlar ve sorular buraya düşer",
            "=> derse basınca hepsi durur",
          ]}
          footer={
            <Link href="/analiz" className="text-cyan-700 dark:text-cyan-300">
              Analize git →
            </Link>
          }
        />
      ) : null}

      {tab === "notes" && notes.length ? (
        <div className="protect-copy space-y-6">
          {notes.map((note, index) => (
            <HumanNoteCard
              key={note.saved_id || note.id}
              {...fromNoteItem(note, index % 2 === 0 ? -1.1 : 0.9)}
              subject={note.subject || subject}
              footer={
                note.video_url_with_t || note.video_url ? (
                  <a
                    href={note.video_url_with_t || note.video_url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    videoya dön → {note.timestamp_label}
                  </a>
                ) : undefined
              }
            />
          ))}
        </div>
      ) : null}

      {tab === "questions" && questions.length ? (
        <div className="space-y-6">
          {questions.map((question) => (
            <QuestionCard
              key={question.saved_id || question.id}
              question={question}
              persona={question.teacher_persona}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}
