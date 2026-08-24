"use client";

import { useState } from "react";
import Link from "next/link";
import { ChevronDown, Loader2 } from "lucide-react";
import { HumanNoteCard } from "@/components/notes/human-note-card";
import { fromNoteItem } from "@/lib/note-format";
import { QuestionCard } from "@/components/analyze/question-card";
import { useAnalyze } from "@/components/analyze/analyze-context";
import { cn } from "@/lib/utils";

export function NotesPanel() {
  const {
    result,
    subject,
    url,
    busy,
    elapsed,
    panelOpen,
    setPanelOpen,
    cancelAnalyze,
  } = useAnalyze();
  const [tab, setTab] = useState<"notes" | "questions">("notes");
  const noteCount = result?.notes.length ?? 0;
  const questionCount = result?.questions.length ?? 0;

  return (
    <section className="overflow-hidden rounded-2xl border border-zinc-200 bg-white/70 dark:border-zinc-800 dark:bg-zinc-950/50">
      <button
        type="button"
        onClick={() => setPanelOpen(!panelOpen)}
        className="flex w-full items-center gap-3 px-4 py-3 text-left"
      >
        <div className="min-w-0 flex-1">
          <p className="font-scribble text-2xl text-amber-800 dark:text-amber-100">
            Ders notları
          </p>
          <p className="truncate text-xs text-zinc-500">
            {busy
              ? result?.notes?.length
                ? `${result.chunks_done ?? 1}/${result.chunks_total ?? 1} dilim hazır · ${elapsed}s`
                : `Hazırlanıyor… ${elapsed}s`
              : result
                ? `${subject || "Ders"} · bu video · ${noteCount} not · ${questionCount} soru`
                : "Analiz bitince burada açılır"}
          </p>
        </div>
        {busy ? <Loader2 className="h-5 w-5 shrink-0 animate-spin text-orange-500" /> : null}
        <ChevronDown
          className={cn(
            "h-5 w-5 shrink-0 text-zinc-500 transition-transform",
            panelOpen && "rotate-180",
          )}
        />
      </button>

      {busy ? (
        <div className="flex justify-end border-t border-zinc-200 px-4 py-2 dark:border-zinc-800">
          <button
            type="button"
            onClick={() => cancelAnalyze()}
            className="text-xs font-medium text-red-600 hover:text-red-800 dark:text-red-400 dark:hover:text-red-300"
          >
            Analizi durdur
          </button>
        </div>
      ) : null}

      {panelOpen ? (
        <div className="border-t border-zinc-200 dark:border-zinc-800">
          {result ? (
            <div className="flex gap-1 px-3 py-2">
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
                Notlar ({noteCount})
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
                Sorular ({questionCount})
              </button>
            </div>
          ) : null}

          <div className="max-h-[min(70vh,36rem)] overflow-y-auto px-4 py-4">
            {!result && busy ? (
              <p className="text-sm text-zinc-500">
                Notlar hazır olunca bu kutunun içinde kaydırarak okursun.
              </p>
            ) : null}
            {!result && !busy ? (
              <p className="text-sm text-zinc-500">
                Henüz analiz yok. Linki yapıştırıp Analiz et’e bas.
              </p>
            ) : null}

            {tab === "notes" && result && noteCount === 0 && busy ? (
              <p className="text-sm text-zinc-500">
                İlk notlar geliyor… Bu kutuda görünecek.
              </p>
            ) : null}
            {tab === "notes" && result && noteCount === 0 && !busy ? (
              <p className="text-sm text-zinc-500">
                Okunacak not yok. Analiz yarım kaldıysa linki tekrar Analiz et.
              </p>
            ) : null}

            {tab === "notes" && result && noteCount > 0 ? (
              <div className="protect-copy space-y-6">
                {url ? (
                  <a
                    href={url}
                    target="_blank"
                    rel="noreferrer"
                    className="block truncate text-xs text-cyan-700 dark:text-cyan-300"
                  >
                    {url}
                  </a>
                ) : null}
                {result.notes.map((note, index) => (
                  <HumanNoteCard
                    key={note.id}
                    {...fromNoteItem(note, index % 2 === 0 ? -1.1 : 0.9)}
                    subject={subject || undefined}
                    footer={
                      <a
                        href={note.video_url_with_t}
                        target="_blank"
                        rel="noreferrer"
                      >
                        videoya dön → {note.timestamp_label}
                      </a>
                    }
                  />
                ))}
              </div>
            ) : null}

            {tab === "notes" && result?.notes?.length ? (
              <div className="border-t border-zinc-200 px-4 py-3 dark:border-zinc-800">
                <Link
                  href="/notlarim"
                  className="inline-flex text-sm font-medium text-orange-700 dark:text-orange-300"
                >
                  Notlarım’a git →
                </Link>
              </div>
            ) : null}

            {tab === "questions" && result ? (
              <div className="space-y-6">
                {result.questions.map((q) => (
                  <QuestionCard
                    key={q.id}
                    question={q}
                    persona={result.teacher_persona}
                  />
                ))}
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </section>
  );
}
