"use client";

import { useEffect, useId, useState, type FormEvent } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { reportQuestion } from "@/lib/api";
import { getUserId } from "@/lib/user";
import { useProfile } from "@/components/profile/profile-context";
import { cn } from "@/lib/utils";

export function ReportQuestionControl({
  questionId,
  className,
}: {
  questionId: string;
  className?: string;
}) {
  const { profile } = useProfile();
  const titleId = useId();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState("");

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, busy]);

  function close() {
    if (busy) return;
    setOpen(false);
    setError("");
    setDone("");
    setReason("");
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    event.stopPropagation();
    setBusy(true);
    setError("");
    try {
      const data = await reportQuestion({
        user_id: getUserId(),
        question_id: questionId,
        reason_text: reason,
      });
      setDone(
        data.message ||
          `Geri bildirimin alındı ${profile.title}, inceleniyor!`,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Gönderilemedi");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={cn("relative z-10", className)}>
      <button
        type="button"
        onClick={(event) => {
          event.preventDefault();
          event.stopPropagation();
          setOpen(true);
          setDone("");
          setError("");
        }}
        className="inline-flex items-center gap-1 rounded-full px-1.5 py-1 text-[11px] font-medium text-zinc-400 transition hover:bg-orange-500/10 hover:text-orange-600 dark:text-zinc-500 dark:hover:text-orange-300"
        aria-label="Hata bildir"
        title="Hata bildir"
      >
        <span aria-hidden>🚩</span>
        <span className="hidden sm:inline">Hata Bildir</span>
      </button>

      {open ? (
        <div
          className="fixed inset-0 z-[80] flex items-center justify-center bg-zinc-950/70 p-4 backdrop-blur-sm"
          onClick={(event) => {
            event.stopPropagation();
            if (event.target === event.currentTarget) close();
          }}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            className="glow-orange relative w-full max-w-md overflow-hidden rounded-2xl border-2 border-orange-400/80 bg-white/85 p-6 backdrop-blur-xl dark:bg-zinc-950/85"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top,_rgba(251,146,60,0.22),transparent_60%)]" />
            <div className="relative space-y-4">
              {done ? (
                <div className="space-y-4">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-orange-600 dark:text-orange-300">
                    Bildirim
                  </p>
                  <p
                    id={titleId}
                    className="text-lg font-medium leading-relaxed text-zinc-900 dark:text-white"
                  >
                    {done}
                  </p>
                  <Button type="button" className="h-11 w-full" onClick={close}>
                    Tamam
                  </Button>
                </div>
              ) : (
                <form className="space-y-4" onSubmit={submit}>
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-orange-600 dark:text-orange-300">
                      Soru Hata Bildir
                    </p>
                    <h2
                      id={titleId}
                      className="mt-1 text-xl font-semibold tracking-tight text-zinc-900 dark:text-white"
                    >
                      Bu soruda ne kaçtı?
                    </h2>
                    <p className="mt-1 text-sm text-zinc-500">
                      Yanlış şık, bozuk metin, konu uyumsuzluğu… kısaca yaz.
                    </p>
                  </div>
                  <textarea
                    value={reason}
                    onChange={(event) => setReason(event.target.value)}
                    required
                    minLength={8}
                    maxLength={2000}
                    rows={5}
                    placeholder="Örn: Doğru şık 1839 olmalı, 1856 Islahat."
                    className="w-full resize-none rounded-xl border border-zinc-300 bg-white px-4 py-3 text-sm text-zinc-900 shadow-inner placeholder:text-zinc-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange-400/70 dark:border-zinc-800 dark:bg-zinc-950/70 dark:text-zinc-100 dark:placeholder:text-zinc-500"
                  />
                  {error ? <p className="text-sm text-red-500">{error}</p> : null}
                  <div className="flex gap-2">
                    <Button type="submit" className="h-11 flex-1" disabled={busy}>
                      {busy ? (
                        <>
                          <Loader2 className="h-4 w-4 animate-spin" />
                          Gönderiliyor
                        </>
                      ) : (
                        "Gönder"
                      )}
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      className="h-11"
                      onClick={close}
                      disabled={busy}
                    >
                      Vazgeç
                    </Button>
                  </div>
                </form>
              )}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
