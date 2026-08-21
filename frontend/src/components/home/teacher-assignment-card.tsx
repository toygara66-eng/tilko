"use client";

import { useEffect, useState } from "react";
import { Loader2, School } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  listStudentAssignments,
  submitStudentAssignment,
  type TeacherAssignment,
} from "@/lib/api";
import { cn } from "@/lib/utils";

export function TeacherAssignmentCard() {
  const [teacherName, setTeacherName] = useState("");
  const [items, setItems] = useState<TeacherAssignment[]>([]);
  const [chosen, setChosen] = useState<Record<number, string>>({});
  const [busy, setBusy] = useState<number | null>(null);
  const [notes, setNotes] = useState<Record<number, string>>({});

  useEffect(() => {
    listStudentAssignments()
      .then((data) => {
        setTeacherName(data.teacher_name || "");
        setItems(data.assignments || []);
      })
      .catch(() => setItems([]));
  }, []);

  if (!items.length) return null;

  async function send(item: TeacherAssignment) {
    const pick = chosen[item.id];
    if (!pick) return;
    setBusy(item.id);
    try {
      const result = await submitStudentAssignment(item.id, pick);
      setNotes((prev) => ({ ...prev, [item.id]: result.message }));
      if (result.correct) {
        setItems((prev) =>
          prev.map((row) => (row.id === item.id ? { ...row, completed: true } : row)),
        );
      }
    } catch (err) {
      setNotes((prev) => ({
        ...prev,
        [item.id]: err instanceof Error ? err.message : "Gönderilemedi",
      }));
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="glow-orange rounded-2xl border-2 border-orange-400/70 bg-white/60 p-5 backdrop-blur-xl dark:bg-zinc-950/50">
      <p className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.22em] text-orange-600 dark:text-orange-300">
        <School className="h-3.5 w-3.5" />
        Hocanın avı
      </p>
      <h2 className="mt-1 text-lg font-semibold text-zinc-900 dark:text-white">
        {teacherName ? `${teacherName} çözmeni istedi` : "Özel soru seti"}
      </h2>
      <div className="mt-4 space-y-4">
        {items.map((item) => (
          <article key={item.id} className="rounded-xl border border-zinc-200 p-3 dark:border-zinc-800">
            <p className="text-xs text-orange-600">{item.topic || item.title}</p>
            <p className="mt-1 text-sm text-zinc-800 dark:text-zinc-200">{item.question_text}</p>
            {item.completed ? (
              <p className="mt-2 text-xs text-emerald-600">Bu avı çözdün.</p>
            ) : (
              <>
                <div className="mt-3 grid gap-1">
                  {Object.entries(item.options || {}).map(([key, label]) => (
                    <button
                      key={key}
                      type="button"
                      onClick={() => setChosen((prev) => ({ ...prev, [item.id]: key }))}
                      className={cn(
                        "rounded-lg border px-3 py-2 text-left text-sm",
                        chosen[item.id] === key
                          ? "border-orange-400 bg-orange-500/15"
                          : "border-zinc-200 dark:border-zinc-800",
                      )}
                    >
                      <span className="font-mono text-xs">{key}</span> {label}
                    </button>
                  ))}
                </div>
                <Button
                  type="button"
                  className="mt-2 h-10"
                  disabled={busy === item.id || !chosen[item.id]}
                  onClick={() => void send(item)}
                >
                  {busy === item.id ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                  Gönder
                </Button>
              </>
            )}
            {notes[item.id] ? (
              <p className="mt-2 text-xs text-zinc-600 dark:text-zinc-400">{notes[item.id]}</p>
            ) : null}
          </article>
        ))}
      </div>
    </section>
  );
}
