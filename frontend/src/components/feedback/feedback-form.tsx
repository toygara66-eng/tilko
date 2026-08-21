"use client";

import { useEffect, useId, useState, type FormEvent } from "react";
import { Lightbulb, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { submitFeedback, type FeedbackCategory } from "@/lib/api";
import { getUserId } from "@/lib/user";
import { useProfile } from "@/components/profile/profile-context";
import { cn } from "@/lib/utils";

const CATEGORIES: { id: FeedbackCategory; label: string }[] = [
  { id: "feature", label: "Özellik Önerisi" },
  { id: "ui_ux", label: "Tasarım" },
  { id: "general", label: "Diğer" },
];

function FeedbackModal({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const { profile } = useProfile();
  const titleId = useId();
  const [category, setCategory] = useState<FeedbackCategory>("feature");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState("");

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, busy, onClose]);

  useEffect(() => {
    if (open) return;
    setText("");
    setError("");
    setDone("");
    setCategory("feature");
    setBusy(false);
  }, [open]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const data = await submitFeedback({
        user_id: getUserId(),
        category,
        message: text,
      });
      setDone(
        data.message ||
          `Teşekkürler ${profile.title}, fikrin inceleme kuyruğuna eklendi!`,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Gönderilemedi");
    } finally {
      setBusy(false);
    }
  }

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center bg-zinc-950/70 p-4 backdrop-blur-sm"
      onClick={(event) => {
        if (event.target === event.currentTarget && !busy) onClose();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="glow-orange relative w-full max-w-md overflow-hidden rounded-2xl border-2 border-orange-400/80 bg-white/85 p-6 backdrop-blur-xl dark:bg-zinc-950/85"
      >
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top,_rgba(251,146,60,0.22),transparent_60%)]" />
        <div className="relative space-y-4">
          {done ? (
            <div className="space-y-4">
              <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-orange-600 dark:text-orange-300">
                Geri bildirim
              </p>
              <p
                id={titleId}
                className="text-lg font-medium leading-relaxed text-zinc-900 dark:text-white"
              >
                {done}
              </p>
              <Button type="button" className="h-11 w-full" onClick={onClose}>
                Tamam
              </Button>
            </div>
          ) : (
            <form className="space-y-4" onSubmit={submit}>
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-orange-600 dark:text-orange-300">
                  Geliştirmemize Yardım Et
                </p>
                <h2
                  id={titleId}
                  className="mt-1 text-xl font-semibold tracking-tight text-zinc-900 dark:text-white"
                >
                  Fikrini bırak, {profile.title}
                </h2>
                <p className="mt-1 text-sm text-zinc-500">
                  Özellik, tasarım veya genel bir not — kuyruğa düşer, okuruz.
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                {CATEGORIES.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => setCategory(item.id)}
                    className={cn(
                      "rounded-full border px-3 py-1.5 text-xs font-medium transition",
                      category === item.id
                        ? "border-orange-500 bg-orange-500/15 text-orange-800 dark:text-orange-200"
                        : "border-zinc-300 text-zinc-500 hover:border-orange-400/60 dark:border-zinc-700 dark:text-zinc-400",
                    )}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
              <textarea
                value={text}
                onChange={(event) => setText(event.target.value)}
                required
                minLength={8}
                maxLength={2000}
                rows={5}
                placeholder={`Fikrini veya önerini yaz ${profile.title}...`}
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
                  onClick={onClose}
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
  );
}

export function FeedbackHeaderButton() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="Geliştirmemize yardım et"
        title="Geliştirmemize yardım et"
        className="rounded-full p-2 text-orange-500 transition hover:bg-orange-500/10 hover:text-orange-400"
      >
        <Lightbulb className="h-5 w-5" />
      </button>
      <FeedbackModal open={open} onClose={() => setOpen(false)} />
    </>
  );
}

export function FeedbackCard() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="glow-orange w-full rounded-2xl border border-orange-400/50 bg-white/60 p-5 text-left backdrop-blur-xl transition hover:border-orange-400 dark:bg-zinc-950/50"
      >
        <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-orange-600 dark:text-orange-300">
          Geri bildirim
        </p>
        <p className="mt-2 text-base font-semibold tracking-tight text-zinc-900 dark:text-white">
          Geliştirmemize Yardım Et 💡
        </p>
        <p className="mt-1 text-sm text-zinc-500">
          Özellik, tasarım veya genel bir fikir bırak. Kuyruğa düşer.
        </p>
      </button>
      <FeedbackModal open={open} onClose={() => setOpen(false)} />
    </>
  );
}
