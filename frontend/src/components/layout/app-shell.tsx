"use client";

import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BookMarked,
  Flame,
  LayoutDashboard,
  LogOut,
  StickyNote,
  Trophy,
  UserRound,
  Youtube,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { TilkoLogo } from "@/components/brand/tilko-logo";
import { NoteModeProvider, NoteModeToggle } from "@/components/notes/note-mode";
import { ThemeProvider, ThemeToggle } from "@/components/theme/theme";
import { ProfileProvider, useProfile } from "@/components/profile/profile-context";
import { PenaltyProvider } from "@/components/pomodoro/penalty-context";
import { PenaltyLock } from "@/components/pomodoro/penalty-lock";
import { PomodoroProvider } from "@/components/pomodoro/pomodoro-context";
import { VictoryStrip } from "@/components/home/victory-strip";
import { KurnazModal } from "@/components/challenge/kurnaz-modal";
import { DiagnosticGate } from "@/components/diagnostic/gate";
import { ExamTargetGate } from "@/components/exam-target/gate";
import { FeedbackHeaderButton } from "@/components/feedback/feedback-form";
import { RoleGate } from "@/components/auth/role-gate";
import { IntegrityGate } from "@/components/security/integrity-gate";
import { AnalyzeProvider } from "@/components/analyze/analyze-context";
import { PlayBillingBoot } from "@/components/billing/play-billing-boot";
import { isSignedIn, logout } from "@/lib/auth";

const NAV = [
  { href: "/", label: "Av", icon: LayoutDashboard },
  { href: "/tuzak-defteri", label: "Defter", icon: BookMarked },
  { href: "/gunluk-gorevler", label: "Görev", icon: Flame },
  { href: "/analiz", label: "Analiz", icon: Youtube },
  { href: "/notlarim", label: "Notlar", icon: StickyNote },
  { href: "/profil", label: "Profil", icon: UserRound },
];

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <ThemeProvider>
      <IntegrityGate>
        <NoteModeProvider>
          <ProfileProvider>
            <AnalyzeProvider>
              <PlayBillingBoot />
              <PenaltyProvider>
                <PomodoroProvider>
                  <ShellFrame>{children}</ShellFrame>
                  <ExamTargetGate />
                  <DiagnosticGate />
                  <RoleGate />
                  <PenaltyLock />
                </PomodoroProvider>
              </PenaltyProvider>
            </AnalyzeProvider>
          </ProfileProvider>
        </NoteModeProvider>
      </IntegrityGate>
    </ThemeProvider>
  );
}

function ShellFrame({ children }: { children: ReactNode }) {
  const path = usePathname();
  const home = path === "/";
  const teshis = path === "/teshis";
  const deneme = path === "/deneme";
  const focused = teshis || deneme;
  const hedef = path === "/hedef";
  const { profile } = useProfile();
  const [boardOpen, setBoardOpen] = useState(false);
  const [signedIn, setSignedIn] = useState(false);
  const giris = path === "/giris";
  const hoca = path === "/hoca";
  const staff = giris || hoca;

  useEffect(() => {
    setSignedIn(isSignedIn());
    const onFocus = () => setSignedIn(isSignedIn());
    window.addEventListener("focus", onFocus);
    window.addEventListener("storage", onFocus);
    return () => {
      window.removeEventListener("focus", onFocus);
      window.removeEventListener("storage", onFocus);
    };
  }, [path]);

  return (
    <div className="flex min-h-screen flex-col bg-zinc-100 text-zinc-900 dark:bg-zinc-950 dark:text-zinc-100">
      {!hedef && !giris ? (
        <>
          <div className="pointer-events-none fixed inset-0 bg-[radial-gradient(ellipse_at_top,_rgba(234,88,12,0.08),transparent_55%)] dark:bg-[radial-gradient(ellipse_at_top,_rgba(34,211,238,0.07),transparent_55%)]" />
          {hoca ? null : <VictoryStrip />}
          <header className="sticky top-0 z-20 border-b border-zinc-200/70 bg-white/65 px-4 py-3 backdrop-blur-xl dark:border-zinc-800/70 dark:bg-zinc-950/65">
            <div className="mx-auto flex max-w-5xl items-center gap-3">
              <Link href={hoca ? "/hoca" : "/"} className="flex shrink-0 items-center gap-2">
                <TilkoLogo size={32} />
                <span className="text-sm font-semibold tracking-tight">TİLKO 🦊</span>
              </Link>
              {hoca ? (
                <span className="hidden text-xs font-medium text-zinc-500 sm:inline">
                  Hoca paneli
                </span>
              ) : (
                <>
                  <Link
                    href="/profil"
                    className="hidden rounded-full border border-orange-400/40 bg-orange-500/10 px-3 py-1 text-xs font-medium text-orange-800 backdrop-blur-md sm:inline-flex dark:text-orange-200"
                  >
                    {profile.title} • {profile.xp} XP
                  </Link>
                  <Link
                    href="/profil"
                    className="inline-flex rounded-full border border-orange-400/40 bg-orange-500/10 px-2.5 py-1 text-[11px] font-medium text-orange-800 sm:hidden dark:text-orange-200"
                  >
                    {profile.xp} XP
                  </Link>
                  <Link
                    href="/pro"
                    className="hidden rounded-full border border-orange-400/50 bg-orange-500/10 px-3 py-1 text-xs font-semibold text-orange-800 sm:inline-flex dark:text-orange-200"
                  >
                    {profile.isPremium ? "Pro" : "Pro'ya geç"}
                  </Link>
                </>
              )}
              <div className="ml-auto flex items-center gap-1">
                {hoca ? null : signedIn ? (
                  <>
                    <span className="hidden rounded-full bg-emerald-500/15 px-3 py-1.5 text-xs font-semibold text-emerald-700 dark:text-emerald-300 sm:inline">
                      Giriş yapıldı
                    </span>
                    <Link
                      href="/profil"
                      className="rounded-full px-3 py-1.5 text-xs font-medium text-zinc-600 hover:text-zinc-900 dark:text-zinc-300 dark:hover:text-white"
                    >
                      Hesabım
                    </Link>
                    <button
                      type="button"
                      onClick={() => {
                        logout();
                        window.location.assign("/giris");
                      }}
                      className="inline-flex items-center gap-1 rounded-full px-2.5 py-1.5 text-xs font-medium text-zinc-500 hover:bg-zinc-100 hover:text-zinc-800 dark:hover:bg-zinc-900 dark:hover:text-zinc-200"
                      title="Çıkış yap"
                    >
                      <LogOut className="h-3.5 w-3.5" />
                      <span className="hidden sm:inline">Çıkış</span>
                    </button>
                  </>
                ) : (
                  <Link
                    href="/giris"
                    className="rounded-full px-3 py-1.5 text-xs font-medium text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200"
                  >
                    Giriş
                  </Link>
                )}
                {hoca ? null : <NoteModeToggle compact />}
                <ThemeToggle className="h-10 w-10 px-0 shadow-none" />
                {hoca ? null : <FeedbackHeaderButton />}
                <button
                  type="button"
                  onClick={() => setBoardOpen(true)}
                  aria-label="Kurnazlar Listesi"
                  className="rounded-full p-2 text-orange-500 transition hover:bg-orange-500/10 hover:text-orange-400"
                  hidden={hoca}
                >
                  <Trophy className="h-5 w-5" />
                </button>
              </div>
            </div>
          </header>
        </>
      ) : null}
      <main
        className={cn(
          "relative mx-auto w-full flex-1",
          hedef || giris
            ? "max-w-none p-0"
            : hoca
              ? "max-w-5xl px-4 pb-10 pt-6 md:px-8"
              : home || focused
                ? "flex max-w-xl flex-col justify-center px-4 pb-24 pt-6 md:pt-10"
                : "max-w-5xl px-4 pb-24 pt-6 md:px-8",
        )}
      >
        {children}
      </main>
      {!hedef && !staff ? (
        <>
          <nav
            className={cn(
              "fixed bottom-4 left-1/2 z-20 flex -translate-x-1/2 gap-0.5 rounded-full border border-zinc-200/80 bg-white/80 p-1 shadow-lg backdrop-blur-xl dark:border-zinc-800 dark:bg-zinc-950/80",
              focused && "hidden",
            )}
          >
            {NAV.map((item) => {
              const active = path === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-label={item.label}
                  className={cn(
                    "rounded-full p-2 transition sm:p-2.5",
                    active
                      ? "bg-orange-500 text-zinc-950"
                      : "text-zinc-500 hover:bg-zinc-100 hover:text-zinc-800 dark:hover:bg-zinc-900 dark:hover:text-zinc-100",
                  )}
                >
                  <item.icon className="h-4 w-4" />
                </Link>
              );
            })}
          </nav>
          <KurnazModal open={boardOpen} onClose={() => setBoardOpen(false)} />
        </>
      ) : null}
    </div>
  );
}
