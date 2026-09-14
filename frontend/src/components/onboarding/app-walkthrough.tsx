"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import {
  BookMarked,
  Flame,
  Lightbulb,
  StickyNote,
  Youtube,
  ChevronRight,
  LayoutDashboard,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useProfile } from "@/components/profile/profile-context";
import { isSignedIn } from "@/lib/auth";
import { hardNavigate, normalizeAppPath } from "@/lib/path";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const STORAGE_KEY = "tilko_app_tour_v2";

const STEPS = [
  {
    id: "analiz",
    icon: Youtube,
    title: "YouTube dersini analiz et",
    body: "Analiz sekmesine git, ders linkini yapıştır. Tilko videoyu not + ÖSYM tarzı soruya çevirir.",
    href: "/analiz",
    cta: "Analiz'e git",
  },
  {
    id: "notlar",
    icon: StickyNote,
    title: "Notlarım arşivi",
    body: "Her analiz ders ders kaydolur. Sete isim ver, PDF indir, tekrar oku.",
    href: "/notlarim",
    cta: "Notlarım'a git",
  },
  {
    id: "defter",
    icon: BookMarked,
    title: "Tuzak defteri",
    body: "Yanlış yaptığın sorular burada birikir. Hoca notu ile çeldiriciyi öğrenirsin.",
    href: "/tuzak-defteri",
    cta: "Deftere git",
  },
  {
    id: "gorev",
    icon: Flame,
    title: "Günlük görev & Sazan Avı",
    body: "Her gün kısa görevler ve hız yarışı. Serini koru, puan topla.",
    href: "/gunluk-gorevler",
    cta: "Görevlere git",
  },
  {
    id: "feedback",
    icon: Lightbulb,
    title: "Fikrini söyle",
    body: "Üst bardaki ampul ikonundan geri bildirim bırak. Önerilerin geliştirme kuyruğuna düşer.",
    href: "/profil",
    cta: "Profile git",
  },
] as const;

export function AppWalkthrough() {
  const path = normalizeAppPath(usePathname());
  const { profile, ready } = useProfile();
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState(0);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!ready || !mounted) return;
    if (!isSignedIn()) return;
    if (profile.role === "teacher" || profile.role === "admin") return;
    if (!profile.isTested) return;
    if (path !== "/") return;
    try {
      if (localStorage.getItem(STORAGE_KEY) === "1") return;
    } catch {
      return;
    }
    setOpen(true);
  }, [ready, mounted, profile.isTested, profile.role, path]);

  function finish() {
    try {
      localStorage.setItem(STORAGE_KEY, "1");
    } catch {
      /* ignore */
    }
    setOpen(false);
  }

  function tryFeature(href: string) {
    finish();
    hardNavigate(href);
  }

  if (!open || !mounted) return null;

  const current = STEPS[step];
  const Icon = current.icon;
  const last = step === STEPS.length - 1;

  return createPortal(
    <div className="fixed inset-0 z-[180] flex items-end justify-center bg-zinc-950/75 p-4 backdrop-blur-sm sm:items-center">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="tilko-tour-title"
        className="glow-orange w-full max-w-md rounded-3xl border-2 border-orange-400/80 bg-white/95 p-6 shadow-xl dark:bg-zinc-950/95"
      >
        <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-orange-600 dark:text-orange-300">
          Tilko turu · {step + 1}/{STEPS.length}
        </p>
        <div className="mt-4 flex items-start gap-4">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-orange-500/15 text-orange-600 dark:text-orange-300">
            <Icon className="h-6 w-6" />
          </div>
          <div className="min-w-0 flex-1">
            <h2
              id="tilko-tour-title"
              className="text-xl font-semibold tracking-tight text-zinc-900 dark:text-white"
            >
              {current.title}
            </h2>
            <p className="mt-2 text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">
              {current.body}
            </p>
          </div>
        </div>

        <div className="mt-5 flex justify-center gap-1.5">
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

        <div className="mt-6 flex flex-col gap-2 sm:flex-row">
          <Button
            type="button"
            className="h-11 flex-1"
            onClick={() => tryFeature(current.href)}
          >
            {current.cta}
            <ChevronRight className="ml-1 h-4 w-4" />
          </Button>
          {!last ? (
            <Button
              type="button"
              variant="outline"
              className="h-11 flex-1"
              onClick={() => setStep((value) => value + 1)}
            >
              Sonraki
            </Button>
          ) : (
            <Button type="button" variant="outline" className="h-11 flex-1" onClick={finish}>
              <LayoutDashboard className="mr-1 h-4 w-4" />
              Ana sayfada kal
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
