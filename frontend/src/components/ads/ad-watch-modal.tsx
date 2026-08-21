"use client";

import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useProfile } from "@/components/profile/profile-context";

const AD_SECONDS = 20;

export function AdWatchModal({
  open,
  onClose,
  onComplete,
}: {
  open: boolean;
  onClose: () => void;
  onComplete: () => void;
}) {
  const { profile } = useProfile();
  const [left, setLeft] = useState(AD_SECONDS);
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (!open) return;
    setLeft(AD_SECONDS);
    setDone(false);
    const id = window.setInterval(() => {
      setLeft((value) => {
        if (value <= 1) {
          window.clearInterval(id);
          setDone(true);
          return 0;
        }
        return value - 1;
      });
    }, 1000);
    return () => window.clearInterval(id);
  }, [open]);

  if (!open) return null;

  const progress = ((AD_SECONDS - left) / AD_SECONDS) * 100;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-zinc-950/70 p-4 backdrop-blur-sm">
      <div className="glow-orange relative w-full max-w-md overflow-hidden rounded-2xl border-2 border-orange-400/80 bg-white/80 p-6 backdrop-blur-xl dark:bg-zinc-950/80">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top,_rgba(251,146,60,0.28),transparent_60%)]" />
        <div className="relative space-y-4">
          <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-orange-600 dark:text-orange-300">
            Reklam · {left}s
          </p>
          <h2 className="text-2xl font-semibold tracking-tight text-zinc-900 dark:text-white">
            Tilko Pro 📺
          </h2>
          <p className="text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">
            40 dakikalık arşivi tek seferde yutma. Pro’da süre yok, kota yok —
            tuzakları önceden gör {profile.title}.
          </p>
          <div className="h-1.5 overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800">
            <div
              className="h-full rounded-full bg-orange-500 shadow-[0_0_12px_rgba(251,146,60,0.7)] transition-all"
              style={{ width: `${progress}%` }}
            />
          </div>
          <div className="flex gap-2">
            {done ? (
              <Button type="button" className="h-11 flex-1" onClick={onComplete}>
                Çevir
              </Button>
            ) : (
              <Button type="button" className="h-11 flex-1" disabled>
                <Loader2 className="h-4 w-4 animate-spin" />
                Reklam bitiyor
              </Button>
            )}
            <Button type="button" variant="outline" className="h-11" onClick={onClose}>
              Vazgeç
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
