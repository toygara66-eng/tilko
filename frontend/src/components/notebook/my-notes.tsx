"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ChevronLeft } from "lucide-react";
import { HumanNoteCard } from "@/components/notes/human-note-card";
import { NoteModeToggle } from "@/components/notes/note-mode";
import { QuestionCard } from "@/components/analyze/question-card";
import { fromNoteItem } from "@/lib/note-format";
import {
  listNotebook,
  type NotebookResponse,
  type SavedNoteItem,
  type SavedQuestionItem,
} from "@/lib/api";
import { getUserId } from "@/lib/user";
import { subjectsFor } from "@/lib/exams";
import { useProfile } from "@/components/profile/profile-context";
import { cn } from "@/lib/utils";

type DayBucket<T> = {
  key: string;
  label: string;
  items: T[];
};

function parseCreated(iso: string | null | undefined): Date | null {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

function dayKeyFromIso(iso: string | null | undefined): string {
  const d = parseCreated(iso);
  if (!d) return "bilinmiyor";
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function formatDayLabel(key: string): string {
  if (key === "bilinmiyor") return "Tarihsiz";
  const d = new Date(`${key}T12:00:00`);
  if (Number.isNaN(d.getTime())) return key;
  return d.toLocaleDateString("tr-TR", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

function formatClock(iso: string | null | undefined): string {
  const d = parseCreated(iso);
  if (!d) return "";
  return d.toLocaleTimeString("tr-TR", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function groupByDay<T extends { created_at?: string | null }>(
  items: T[],
): DayBucket<T>[] {
  const map = new Map<string, T[]>();
  for (const item of items) {
    const key = dayKeyFromIso(item.created_at);
    const bag = map.get(key) || [];
    bag.push(item);
    map.set(key, bag);
  }
  const keys = [...map.keys()].sort((a, b) => {
    if (a === "bilinmiyor") return 1;
    if (b === "bilinmiyor") return -1;
    return b.localeCompare(a);
  });
  return keys.map((key) => {
    const bag = map.get(key) || [];
    bag.sort((a, b) => {
      const ta = parseCreated(a.created_at)?.getTime() ?? 0;
      const tb = parseCreated(b.created_at)?.getTime() ?? 0;
      return ta - tb;
    });
    return { key, label: formatDayLabel(key), items: bag };
  });
}

function groupByHour<T extends { created_at?: string | null }>(
  items: T[],
): { label: string; items: T[] }[] {
  const map = new Map<string, T[]>();
  for (const item of items) {
    const d = parseCreated(item.created_at);
    const hourLabel = d
      ? `${String(d.getHours()).padStart(2, "0")}:00`
      : "Saat yok";
    const bag = map.get(hourLabel) || [];
    bag.push(item);
    map.set(hourLabel, bag);
  }
  const keys = [...map.keys()].sort((a, b) => {
    if (a === "Saat yok") return 1;
    if (b === "Saat yok") return -1;
    return a.localeCompare(b);
  });
  return keys.map((key) => ({
    label: key === "Saat yok" ? key : `${key} civarı`,
    items: map.get(key) || [],
  }));
}

export function MyNotes() {
  const { profile } = useProfile();
  const examSubjects = subjectsFor(profile.examTarget || "kpss_lisans");
  const [subject, setSubject] = useState<string | null>(null);
  const [dayKey, setDayKey] = useState<string | null>(null);
  const [tab, setTab] = useState<"notes" | "questions">("notes");
  const [data, setData] = useState<NotebookResponse | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(true);

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

  const notes = (subject ? data?.notes : []) || [];
  const questions = (subject ? data?.questions : []) || [];
  const noteDays = useMemo(() => groupByDay(notes), [notes]);
  const questionDays = useMemo(() => groupByDay(questions), [questions]);
  const activeDays = tab === "notes" ? noteDays : questionDays;
  const dayBucket = dayKey
    ? activeDays.find((d) => d.key === dayKey) || null
    : null;

  const pickSubject = (name: string) => {
    setSubject(name);
    setDayKey(null);
  };

  const backToSubjects = () => {
    setSubject(null);
    setDayKey(null);
  };

  const backToDays = () => setDayKey(null);

  const emptyArchive =
    !busy &&
    !subject &&
    chips.every((s) => s.note_count === 0 && s.question_count === 0);

  const emptySubject =
    !busy &&
    !!subject &&
    !dayKey &&
    notes.length === 0 &&
    questions.length === 0;

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h1 className="font-scribble text-3xl text-amber-800 dark:text-amber-100 sm:text-4xl md:text-5xl">
            Notlarım
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-zinc-600 dark:text-zinc-400 sm:text-base">
            Ders seç → tarihi aç → o gün çıkarılan notlar saate göre sıralı durur.
            Analiz sayfasında yalnızca o anki video görünür.
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
          {dayKey ? (
            <>
              <button
                type="button"
                onClick={backToDays}
                className="rounded-lg px-2 py-1 font-medium text-amber-800 hover:bg-orange-50 dark:text-amber-100 dark:hover:bg-zinc-800"
              >
                {subject}
              </button>
              <span className="text-zinc-400">/</span>
              <span className="rounded-lg px-2 py-1 font-medium text-zinc-900 dark:text-zinc-100">
                {formatDayLabel(dayKey)}
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

      {subject && !dayKey ? (
        <>
          <div className="flex gap-1">
            <button
              type="button"
              onClick={() => {
                setTab("notes");
                setDayKey(null);
              }}
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
              onClick={() => {
                setTab("questions");
                setDayKey(null);
              }}
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

          {activeDays.length ? (
            <div className="space-y-2">
              <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">
                Tarihler
              </p>
              <div className="grid gap-2 sm:grid-cols-2">
                {activeDays.map((day) => (
                  <button
                    key={day.key}
                    type="button"
                    onClick={() => setDayKey(day.key)}
                    className="flex items-center justify-between rounded-xl border border-zinc-300 bg-white/50 px-4 py-3 text-left transition hover:border-orange-400/70 dark:border-zinc-700 dark:bg-zinc-900/40"
                  >
                    <span className="capitalize text-sm font-medium text-zinc-800 dark:text-zinc-100">
                      {day.label}
                    </span>
                    <span className="text-xs text-zinc-500">
                      {day.items.length} {tab === "notes" ? "not" : "soru"}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          ) : null}
        </>
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
            "=> derse bas, tarihi aç, saate göre oku",
          ]}
          footer={
            <Link href="/analiz" className="text-cyan-700 dark:text-cyan-300">
              Analize git →
            </Link>
          }
        />
      ) : null}

      {emptySubject ? (
        <HumanNoteCard
          title="Bu ders henüz boş"
          tilt={-0.6}
          lines={[
            "-> Analiz’de bu dersi seçip video çevir",
            "=> notlar bu dersin altına düşer",
          ]}
          footer={
            <Link href="/analiz" className="text-cyan-700 dark:text-cyan-300">
              Analize git →
            </Link>
          }
        />
      ) : null}

      {subject && dayKey && dayBucket && tab === "notes" ? (
        <DayNotesList
          subject={subject}
          items={dayBucket.items as SavedNoteItem[]}
        />
      ) : null}

      {subject && dayKey && dayBucket && tab === "questions" ? (
        <DayQuestionsList items={dayBucket.items as SavedQuestionItem[]} />
      ) : null}

      {subject && dayKey && !busy && dayBucket && dayBucket.items.length === 0 ? (
        <p className="text-sm text-zinc-500">Bu günde kayıt yok.</p>
      ) : null}
    </div>
  );
}

function DayNotesList({
  subject,
  items,
}: {
  subject: string;
  items: SavedNoteItem[];
}) {
  const hours = groupByHour(items);
  return (
    <div className="protect-copy space-y-6">
      {hours.map((hour) => (
        <section key={hour.label} className="space-y-4">
          <h2 className="sticky top-0 z-10 -mx-1 border-b border-zinc-200/80 bg-white/90 px-1 py-2 text-sm font-medium text-zinc-600 backdrop-blur dark:border-zinc-800/80 dark:bg-zinc-950/90 dark:text-zinc-400">
            {hour.label}
          </h2>
          {hour.items.map((note, index) => (
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
                    {formatClock(note.created_at)
                      ? ` · ${formatClock(note.created_at)}`
                      : ""}
                  </a>
                ) : undefined
              }
            />
          ))}
        </section>
      ))}
    </div>
  );
}

function DayQuestionsList({ items }: { items: SavedQuestionItem[] }) {
  const hours = groupByHour(items);
  return (
    <div className="space-y-6">
      {hours.map((hour) => (
        <section key={hour.label} className="space-y-4">
          <h2 className="sticky top-0 z-10 -mx-1 border-b border-zinc-200/80 bg-white/90 px-1 py-2 text-sm font-medium text-zinc-600 backdrop-blur dark:border-zinc-800/80 dark:bg-zinc-950/90 dark:text-zinc-400">
            {hour.label}
          </h2>
          {hour.items.map((question) => (
            <QuestionCard
              key={question.saved_id || question.id}
              question={question}
              persona={question.teacher_persona}
            />
          ))}
        </section>
      ))}
    </div>
  );
}
