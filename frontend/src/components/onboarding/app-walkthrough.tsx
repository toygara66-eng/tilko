"use client";

import { useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import {
  BookMarked,
  ChevronLeft,
  ChevronRight,
  Flame,
  LayoutDashboard,
  Lightbulb,
  Sparkles,
  StickyNote,
  UserRound,
  Youtube,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useProfile } from "@/components/profile/profile-context";
import { isSignedIn } from "@/lib/auth";
import { normalizeAppPath } from "@/lib/path";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

export const TOUR_STORAGE_KEY = "tilko_app_tour_v3";

type Step = {
  id: string;
  title: string;
  body: string;
  /** `data-tour` değeri; yoksa ortada karşılama kartı */
  target?: string;
  icon: typeof Sparkles;
};

const STEPS: Step[] = [
  {
    id: "welcome",
    icon: Sparkles,
    title: "Tilko’ya hoş geldin",
    body: "YouTube dersini not + ÖSYM tarzı soruya çeviren av arkadaşın. Kısa turda menüyü gezelim.",
  },
  {
    id: "av",
    icon: LayoutDashboard,
    title: "Av — ana üs",
    body: "Günlük av, seriler ve hızlı giriş buradan. Eve dönmek için bu ikona bas.",
    target: "nav-av",
  },
  {
    id: "analiz",
    icon: Youtube,
    title: "Analiz",
    body: "Ders linkini yapıştır. Tilko altyazıdan öğretici not ve sınav sorusu çıkarır.",
    target: "nav-analiz",
  },
  {
    id: "notlar",
    icon: StickyNote,
    title: "Notlarım",
    body: "Her analiz burada arşivlenir. Sete isim ver, tekrar oku, PDF indir.",
    target: "nav-notlar",
  },
  {
    id: "defter",
    icon: BookMarked,
    title: "Tuzak defteri",
    body: "Yanlışların burada birikir. Çeldiriciyi hoca notuyla öğrenirsin.",
    target: "nav-defter",
  },
  {
    id: "gorev",
    icon: Flame,
    title: "Günlük görev",
    body: "Kısa görevler ve Sazan Avı. Serini koru, XP topla.",
    target: "nav-gorev",
  },
  {
    id: "profil",
    icon: UserRound,
    title: "Profil",
    body: "XP, hedef sınav, seviye rotası ve ayarlar burada.",
    target: "nav-profil",
  },
  {
    id: "feedback",
    icon: Lightbulb,
    title: "Fikrini söyle",
    body: "Üst bardaki ampul: özellik / tasarım önerin doğrudan geliştirme kuyruğuna düşer.",
    target: "header-feedback",
  },
];

type Hole = { top: number; left: number; width: number; height: number };

function measureTarget(id: string): Hole | null {
  if (typeof document === "undefined") return null;
  const el = document.querySelector(`[data-tour="${id}"]`);
  if (!(el instanceof HTMLElement)) return null;
  const r = el.getBoundingClientRect();
  if (r.width < 4 || r.height < 4) return null;
  const pad = 10;
  return {
    top: Math.max(8, r.top - pad),
    left: Math.max(8, r.left - pad),
    width: Math.min(window.innerWidth - 16, r.width + pad * 2),
    height: Math.min(window.innerHeight - 16, r.height + pad * 2),
  };
}

export function AppWalkthrough() {
  const path = normalizeAppPath(usePathname());
  const { profile, ready } = useProfile();
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState(0);
  const [mounted, setMounted] = useState(false);
  const [hole, setHole] = useState<Hole | null>(null);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!ready || !mounted) return;
    if (!isSignedIn()) return;
    if (profile.role === "teacher" || profile.role === "admin") return;
    // Hedef + teşhis bittikten sonra ilk gerçek giriş
    if (!profile.isTested) return;
    if (path !== "/") return;
    try {
      if (localStorage.getItem(TOUR_STORAGE_KEY) === "1") return;
    } catch {
      return;
    }
    const t = window.setTimeout(() => setOpen(true), 450);
    return () => window.clearTimeout(t);
  }, [ready, mounted, profile.isTested, profile.role, path]);

  // Profil’den “turu tekrar göster”
  useEffect(() => {
    const onReplay = () => {
      setStep(0);
      setOpen(true);
    };
    window.addEventListener("tilko-replay-tour", onReplay);
    return () => window.removeEventListener("tilko-replay-tour", onReplay);
  }, []);

  const current = STEPS[step];
  const last = step === STEPS.length - 1;

  const refreshHole = useCallback(() => {
    if (!open || !current?.target) {
      setHole(null);
      return;
    }
    setHole(measureTarget(current.target));
  }, [open, current?.target]);

  useEffect(() => {
    refreshHole();
    if (!open) return;
    const onResize = () => refreshHole();
    window.addEventListener("resize", onResize);
    window.addEventListener("orientationchange", onResize);
    const id = window.setInterval(refreshHole, 400);
    return () => {
      window.removeEventListener("resize", onResize);
      window.removeEventListener("orientationchange", onResize);
      window.clearInterval(id);
    };
  }, [open, step, refreshHole]);

  function finish() {
    try {
      localStorage.setItem(TOUR_STORAGE_KEY, "1");
    } catch {
      /* ignore */
    }
    setOpen(false);
    setStep(0);
  }

  if (!open || !mounted) return null;

  const Icon = current.icon;
  const tooltipAbove = hole ? hole.top > window.innerHeight * 0.45 : false;

  return createPortal(
    <div className="fixed inset-0 z-[180]" role="dialog" aria-modal="true" aria-labelledby="tilko-tour-title">
      {hole ? (
        <>
          <button
            type="button"
            aria-label="Turu kapat"
            className="absolute inset-0 cursor-default bg-transparent"
            onClick={finish}
          />
          <div
            className="pointer-events-none absolute rounded-2xl ring-2 ring-orange-400 transition-all duration-300"
            style={{
              top: hole.top,
              left: hole.left,
              width: hole.width,
              height: hole.height,
              boxShadow: "0 0 0 9999px rgba(9,9,11,0.72)",
            }}
          />
        </>
      ) : (
        <button
          type="button"
          aria-label="Turu kapat"
          className="absolute inset-0 cursor-default bg-zinc-950/70 backdrop-blur-[2px]"
          onClick={finish}
        />
      )}

      {/* Kart */}
      <div
        className={cn(
          "absolute z-10 w-[min(100%-2rem,22rem)] rounded-3xl border-2 border-orange-400/80 bg-white p-5 shadow-xl dark:bg-zinc-950",
          !hole && "left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2",
          hole && "left-1/2 -translate-x-1/2",
        )}
        style={
          hole
            ? tooltipAbove
              ? { bottom: Math.max(16, window.innerHeight - hole.top + 12) }
              : {
                  top: Math.min(
                    window.innerHeight - 280,
                    hole.top + hole.height + 12,
                  ),
                }
            : undefined
        }
        onClick={(e) => e.stopPropagation()}
      >
        <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-orange-600 dark:text-orange-300">
          Tilko turu · {step + 1}/{STEPS.length}
        </p>
        <div className="mt-3 flex items-start gap-3">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-orange-500/15 text-orange-600 dark:text-orange-300">
            <Icon className="h-5 w-5" />
          </div>
          <div className="min-w-0 flex-1">
            <h2
              id="tilko-tour-title"
              className="text-lg font-semibold tracking-tight text-zinc-900 dark:text-white"
            >
              {current.title}
            </h2>
            <p className="mt-1.5 text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">
              {current.body}
            </p>
          </div>
        </div>

        <div className="mt-4 flex justify-center gap-1.5">
          {STEPS.map((item, index) => (
            <button
              key={item.id}
              type="button"
              aria-label={`Adım ${index + 1}`}
              onClick={() => setStep(index)}
              className={cn(
                "h-2 rounded-full transition-all",
                index === step ? "w-6 bg-orange-500" : "w-2 bg-zinc-300 dark:bg-zinc-700",
              )}
            />
          ))}
        </div>

        <div className="mt-5 flex gap-2">
          {step > 0 ? (
            <Button
              type="button"
              variant="outline"
              className="h-11 shrink-0 px-3"
              onClick={() => setStep((v) => v - 1)}
              aria-label="Önceki"
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
          ) : null}
          {!last ? (
            <Button
              type="button"
              className="h-11 flex-1"
              onClick={() => setStep((v) => v + 1)}
            >
              Sonraki
              <ChevronRight className="ml-1 h-4 w-4" />
            </Button>
          ) : (
            <Button type="button" className="h-11 flex-1" onClick={finish}>
              Tamam, başla
            </Button>
          )}
        </div>
        <button
          type="button"
          onClick={finish}
          className="mt-3 w-full text-center text-xs font-medium text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300"
        >
          Turu atla
        </button>
      </div>
    </div>,
    document.body,
  );
}
