"use client";

import { useEffect, useMemo, useState } from "react";
import { ChevronLeft, Download, Pencil } from "lucide-react";
import { HumanNoteCard } from "@/components/notes/human-note-card";
import { NoteModeToggle } from "@/components/notes/note-mode";
import { QuestionCard } from "@/components/analyze/question-card";
import { fromNoteItem } from "@/lib/note-format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  downloadNotebookPdf,
  listNotebook,
  renameNotebookSession,
  type NotebookResponse,
  type NotebookSessionItem,
  type SavedNoteItem,
  type SavedQuestionItem,
} from "@/lib/api";
import { getUserId } from "@/lib/user";
import { subjectsFor } from "@/lib/exams";
import { useProfile } from "@/components/profile/profile-context";
import { cn } from "@/lib/utils";

export function MyNotes() {
  const { profile } = useProfile();
  const examSubjects = subjectsFor(profile.examTarget || "kpss_lisans");
  const [subject, setSubject] = useState<string | null>(null);
  const [videoId, setVideoId] = useState<string | null>(null);
  const [tab, setTab] = useState<"notes" | "questions">("notes");
  const [data, setData] = useState<NotebookResponse | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(true);
  const [renameOpen, setRenameOpen] = useState(false);
  const [renameValue, setRenameValue] = useState("");
  const [renameBusy, setRenameBusy] = useState(false);
  const [pdfBusy, setPdfBusy] = useState(false);

  const chips = useMemo(() => {
    const counts = new Map(
      (data?.subjects || []).map((item) => [item.name, item] as const),
    );
    const names = [
      ...examSubjects,
      ...(data?.subjects || [])
        .map((item) => item.name)
        .filter((name) => !examSubjects.includes(name)),
    ];
    return names.map(
      (name) => counts.get(name) || { name, note_count: 0, question_count: 0 },
    );
  }, [data, examSubjects]);

  const sessions = useMemo(() => {
    const list = data?.sessions || [];
    if (!subject) return list;
    return list.filter((s) => s.subject === subject);
  }, [data, subject]);

  const activeSession = useMemo(
    () => sessions.find((s) => s.video_id === videoId) || null,
    [sessions, videoId],
  );

  useEffect(() => {
    let live = true;
    function load() {
      setBusy(true);
      listNotebook(getUserId(), subject || undefined)
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

  const notes = useMemo(() => {
    const all = (subject ? data?.notes : []) || [];
    if (!videoId) return all;
    return all.filter((n) => (n.video_id || "") === videoId);
  }, [data, subject, videoId]);

  const questions = useMemo(() => {
    const all = (subject ? data?.questions : []) || [];
    if (!videoId) return all;
    return all.filter((q) => (q.video_id || "") === videoId);
  }, [data, subject, videoId]);

  const pickSubject = (name: string) => {
    setSubject(name);
    setVideoId(null);
  };

  const backToSubjects = () => {
    setSubject(null);
    setVideoId(null);
  };

  const backToSessions = () => setVideoId(null);

  const emptyArchive =
    !busy &&
    !subject &&
    chips.every((s) => s.note_count === 0 && s.question_count === 0);

  const emptySubject =
    !busy &&
    !!subject &&
    !videoId &&
    sessions.length === 0 &&
    notes.length === 0 &&
    questions.length === 0;

  async function saveRename() {
    if (!subject || !videoId || renameValue.trim().length < 2) return;
    setRenameBusy(true);
    try {
      await renameNotebookSession({
        user_id: getUserId(),
        subject,
        video_id: videoId,
        label: renameValue.trim(),
        video_url: activeSession?.video_url || notes[0]?.video_url || "",
      });
      setRenameOpen(false);
      const payload = await listNotebook(getUserId(), subject);
      setData(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "İsim kaydedilemedi");
    } finally {
      setRenameBusy(false);
    }
  }

  async function exportPdf() {
    if (!subject || !videoId) return;
    setPdfBusy(true);
    try {
      await downloadNotebookPdf({
        userId: getUserId(),
        subject,
        videoId,
        filename: activeSession?.label || subject,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "PDF indirilemedi");
    } finally {
      setPdfBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h1 className="font-scribble text-3xl text-amber-800 dark:text-amber-100 sm:text-4xl md:text-5xl">
            Notlarım
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-zinc-600 dark:text-zinc-400 sm:text-base">
            Ders seç → not setine isim ver → PDF indir. Örn: “Türkçe · Aker Kartal
            ekler konu anlatımı”.
          </p>
        </div>
        <NoteModeToggle className="self-start" />
      </div>

      {subject ? (
        <nav className="flex flex-wrap items-center gap-2 text-sm text-zinc-600 dark:text-zinc-400">
          <button
            type="button"
            onClick={backToSubjects}
            className="inline-flex items-center gap-1 rounded-lg px-2 py-1 hover:bg-zinc-100 dark:hover:bg-zinc-800"
          >
            <ChevronLeft className="h-4 w-4" />
            Dersler
          </button>
          <span className="text-zinc-400">/</span>
          {videoId ? (
            <>
              <button
                type="button"
                onClick={backToSessions}
                className="rounded-lg px-2 py-1 font-medium text-amber-800 hover:bg-orange-50 dark:text-amber-100 dark:hover:bg-zinc-800"
              >
                {subject}
              </button>
              <span className="text-zinc-400">/</span>
              <span className="max-w-[14rem] truncate rounded-lg px-2 py-1 font-medium text-zinc-900 dark:text-zinc-100 sm:max-w-xs">
                {activeSession?.label || "Not seti"}
              </span>
            </>
          ) : (
            <span className="rounded-lg px-2 py-1 font-medium text-zinc-900 dark:text-zinc-100">
              {subject}
            </span>
          )}
        </nav>
      ) : null}

      {!subject ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {chips.map((chip) => {
            const total = chip.note_count + chip.question_count;
            return (
              <button
                key={chip.name}
                type="button"
                onClick={() => pickSubject(chip.name)}
                className={cn(
                  "rounded-2xl border px-4 py-4 text-left transition",
                  "border-zinc-300 bg-white/50 hover:border-orange-400/70 dark:border-zinc-700 dark:bg-zinc-900/40",
                  total === 0 && "opacity-60",
                )}
              >
                <p className="font-scribble text-2xl text-amber-800 dark:text-amber-100">
                  {chip.name}
                </p>
                <p className="mt-1 text-xs text-zinc-500">
                  {chip.note_count} not · {chip.question_count} soru
                </p>
              </button>
            );
          })}
        </div>
      ) : null}

      {subject && !videoId ? (
        <div className="space-y-2">
          <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">
            Not setleri
          </p>
          {sessions.length ? (
            <div className="grid gap-2 sm:grid-cols-2">
              {sessions.map((session) => (
                <SessionCard
                  key={`${session.subject}-${session.video_id}`}
                  session={session}
                  onOpen={() => setVideoId(session.video_id)}
                />
              ))}
            </div>
          ) : null}
        </div>
      ) : null}

      {subject && videoId ? (
        <div className="space-y-4">
          <div className="flex flex-col gap-3 rounded-2xl border border-orange-300/50 bg-orange-50/60 p-4 dark:border-orange-500/30 dark:bg-orange-950/20 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              <p className="text-xs font-medium uppercase tracking-wide text-orange-700 dark:text-orange-300">
                {subject}
              </p>
              <h2 className="truncate text-lg font-semibold text-zinc-900 dark:text-white">
                {activeSession?.label || "İsimsiz not seti"}
              </h2>
              <p className="mt-1 text-xs text-zinc-500">
                {notes.length} not · {questions.length} soru
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                variant="outline"
                className="h-10"
                onClick={() => {
                  setRenameValue(activeSession?.label || "");
                  setRenameOpen(true);
                }}
              >
                <Pencil className="h-4 w-4" />
                İsim ver
              </Button>
              <Button
                type="button"
                className="h-10"
                disabled={pdfBusy || notes.length === 0}
                onClick={() => void exportPdf()}
              >
                <Download className="h-4 w-4" />
                {pdfBusy ? "Hazırlanıyor…" : "PDF indir"}
              </Button>
            </div>
          </div>

          {renameOpen ? (
            <div className="rounded-2xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
              <p className="text-sm font-medium text-zinc-800 dark:text-zinc-100">
                Bu sete bir isim ver
              </p>
              <p className="mt-1 text-xs text-zinc-500">
                Örn: Aker Kartal ekler konu anlatımı
              </p>
              <Input
                className="mt-3"
                value={renameValue}
                maxLength={160}
                placeholder={`${subject} · konu anlatımı`}
                onChange={(e) => setRenameValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") void saveRename();
                }}
              />
              <div className="mt-3 flex gap-2">
                <Button
                  type="button"
                  className="h-10"
                  disabled={renameBusy || renameValue.trim().length < 2}
                  onClick={() => void saveRename()}
                >
                  {renameBusy ? "Kaydediliyor…" : "Kaydet"}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  className="h-10"
                  onClick={() => setRenameOpen(false)}
                >
                  Vazgeç
                </Button>
              </div>
            </div>
          ) : null}

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

          {tab === "notes" ? (
            <SessionNotesList notes={notes} />
          ) : (
            <SessionQuestionsList questions={questions} />
          )}
        </div>
      ) : null}

      {error ? <p className="text-sm text-red-400">{error}</p> : null}
      {busy ? <p className="text-sm text-zinc-500">Notlar yükleniyor…</p> : null}

      {emptyArchive ? (
        <HumanNoteCard
          title="Henüz arşiv yok"
          tilt={-0.6}
          lines={[
            "-> Analiz’den bir video çevir",
            "=> notlar buraya ders ders birikir",
            "=> sete isim verip PDF indirebilirsin",
          ]}
          warning="İlk analizin en değerli notun."
        />
      ) : null}

      {emptySubject ? (
        <HumanNoteCard
          title={`${subject} boş`}
          tilt={0.5}
          lines={[
            "-> Bu derste henüz kayıt yok",
            "=> Analiz’de dersi seçip video çevir",
          ]}
        />
      ) : null}
    </div>
  );
}

function SessionCard({
  session,
  onOpen,
}: {
  session: NotebookSessionItem;
  onOpen: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className="flex flex-col rounded-xl border border-zinc-300 bg-white/50 px-4 py-3 text-left transition hover:border-orange-400/70 dark:border-zinc-700 dark:bg-zinc-900/40"
    >
      <span className="line-clamp-2 text-sm font-semibold text-zinc-900 dark:text-zinc-100">
        {session.label || "İsimsiz not seti"}
      </span>
      <span className="mt-1 text-xs text-zinc-500">
        {session.note_count} not · {session.question_count} soru
      </span>
    </button>
  );
}

function SessionNotesList({ notes }: { notes: SavedNoteItem[] }) {
  if (!notes.length) {
    return <p className="text-sm text-zinc-500">Bu sette not yok.</p>;
  }
  return (
    <div className="space-y-4">
      {notes.map((note, index) => (
        <HumanNoteCard
          key={note.saved_id || note.id}
          {...fromNoteItem(note, index % 2 === 0 ? -1.1 : 0.9)}
        />
      ))}
    </div>
  );
}

function SessionQuestionsList({
  questions,
}: {
  questions: SavedQuestionItem[];
}) {
  if (!questions.length) {
    return <p className="text-sm text-zinc-500">Bu sette soru yok.</p>;
  }
  return (
    <div className="space-y-4">
      {questions.map((item) => (
        <QuestionCard key={item.saved_id || item.id} question={item} />
      ))}
    </div>
  );
}
