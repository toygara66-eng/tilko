"use client";

import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BookMarked,
  Flame,
  LayoutDashboard,
  Loader2,
  LogOut,
  StickyNote,
  Trophy,
  UserRound,
  Youtube,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { hardNavigate, normalizeAppPath } from "@/lib/path";
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
import { AuthGate, isAuthPublicPath } from "@/components/auth/auth-gate";
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
                  <AuthGate />
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
  const path = normalizeAppPath(usePathname());
  const home = path === "/";
  const teshis = path === "/teshis";
  const deneme = path === "/deneme";
  const focused = teshis || deneme;
  const hedef = path === "/hedef";
  const { profile } = useProfile();
  const [boardOpen, setBoardOpen] = useState(false);
  const [signedIn, setSignedIn] = useState(false);
  const [authOk, setAuthOk] = useState(() => {
    if (typeof window === "undefined") return true;
    return isAuthPublicPath(path) || isSignedIn();
  });
  const giris = path === "/giris";
  const gizlilik = path === "/gizlilik";
  const hakkinda = path === "/hakkinda";
  const hesapSil = path === "/hesap-sil";
  const hoca = path === "/hoca";
  const staff = giris || hoca || gizlilik || hakkinda || hesapSil;
  const hideChrome = hedef || giris || gizlilik || hakkinda || hesapSil;

  useEffect(() => {
    const ok = isAuthPublicPath(path) || isSignedIn();
    setAuthOk(ok);
    setSignedIn(isSignedIn());
    const onFocus = () => {
      setSignedIn(isSignedIn());
      setAuthOk(isAuthPublicPath(path) || isSignedIn());
    };
    const onGate = (ev: Event) => {
      const detail = (ev as CustomEvent<{ allowed?: boolean }>).detail;
      if (typeof detail?.allowed === "boolean") setAuthOk(detail.allowed);
    };
    window.addEventListener("focus", onFocus);
    window.addEventListener("storage", onFocus);
    window.addEventListener("tilko-auth-gate", onGate as EventListener);
    return () => {
      window.removeEventListener("focus", onFocus);
      window.removeEventListener("storage", onFocus);
      window.removeEventListener("tilko-auth-gate", onGate as EventListener);
    };
  }, [path]);

  // Girişsiz kullanıcıya ana uygulama içeriğini (Laboratuvar vb.) gösterme.
  if (!authOk && !isAuthPublicPath(path)) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-100 dark:bg-zinc-950">
        <Loader2 className="h-6 w-6 animate-spin text-orange-500" />
      </div>
    );
  }

  return (
    <div className="flex min-h-[100dvh] w-full max-w-[100vw] flex-col overflow-x-hidden bg-zinc-100 text-zinc-900 dark:bg-zinc-950 dark:text-zinc-100">
      {!hideChrome ? (
        <>
          <div className="pointer-events-none fixed inset-0 bg-[radial-gradient(ellipse_at_top,_rgba(234,88,12,0.08),transparent_55%)] dark:bg-[radial-gradient(ellipse_at_top,_rgba(34,211,238,0.07),transparent_55%)]" />
          {hoca ? null : <VictoryStrip />}
          {/* Android WebView: backdrop-blur + yarı saydam bg bazen tamamen görünmez yapıyor */}
          <header className="sticky top-0 z-40 border-b border-zinc-200 bg-white px-2 py-2 pt-[max(0.5rem,env(safe-area-inset-top))] dark:border-zinc-800 dark:bg-zinc-950 sm:px-4 sm:py-3">
            <div className="mx-auto flex w-full min-w-0 max-w-5xl items-center gap-1.5 sm:gap-3">
              <Link
                href={hoca ? "/hoca" : "/"}
                className="flex min-w-0 shrink items-center gap-1.5 sm:gap-2"
              >
                <TilkoLogo size={28} className="shrink-0" />
                <span className="truncate text-sm font-semibold tracking-tight text-zinc-900 dark:text-zinc-100">
                  TİLKO
                </span>
              </Link>
              {hoca ? (
                <span className="hidden text-xs font-medium text-zinc-500 sm:inline">
                  Hoca paneli
                </span>
              ) : (
                <Link
                  href="/profil"
                  className="hidden min-w-0 truncate rounded-full border border-orange-400/40 bg-orange-500/10 px-2.5 py-1 text-[11px] font-medium text-orange-800 sm:inline-flex dark:text-orange-200"
                >
                  {profile.xp} XP
                </Link>
              )}
              <div className="ml-auto flex min-w-0 shrink-0 items-center gap-0.5 sm:gap-1">
                {hoca ? null : signedIn ? (
                  <>
                    <Link
                      href="/profil"
                      className="hidden rounded-full px-2 py-1.5 text-xs font-medium text-zinc-600 hover:text-zinc-900 sm:inline dark:text-zinc-300 dark:hover:text-white"
                    >
                      Hesabım
                    </Link>
                    <button
                      type="button"
                      onClick={() => {
                        logout();
                        hardNavigate("/giris");
                      }}
                      className="inline-flex items-center gap-1 rounded-full p-2 text-xs font-medium text-zinc-500 hover:bg-zinc-100 hover:text-zinc-800 dark:hover:bg-zinc-900 dark:hover:text-zinc-200 sm:px-2.5 sm:py-1.5"
                      title="Çıkış yap"
                    >
                      <LogOut className="h-3.5 w-3.5" />
                      <span className="hidden sm:inline">Çıkış</span>
                    </button>
                  </>
                ) : (
                  <Link
                    href="/giris"
                    className="rounded-full px-2 py-1.5 text-xs font-medium text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200"
                  >
                    Giriş
                  </Link>
                )}
                {hoca ? null : <NoteModeToggle compact />}
                <ThemeToggle className="h-9 w-9 shrink-0 px-0 shadow-none sm:h-10 sm:w-10" />
                {hoca ? null : <FeedbackHeaderButton />}
                <button
                  type="button"
                  onClick={() => setBoardOpen(true)}
                  aria-label="Kurnazlar Listesi"
                  className="shrink-0 rounded-full p-2 text-orange-500 transition hover:bg-orange-500/10 hover:text-orange-400"
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
          "relative mx-auto w-full min-w-0 max-w-full flex-1 overflow-x-hidden overflow-y-auto",
          hideChrome
            ? "max-w-none p-0"
            : hoca
              ? "max-w-5xl px-3 pb-10 pt-6 sm:px-4 md:px-8"
              : home || focused
                ? "flex max-w-xl flex-col justify-start px-3 pb-28 pt-4 sm:px-4 md:pt-6"
                : "max-w-5xl px-3 pb-28 pt-6 sm:px-4 md:px-8",
        )}
      >
        {children}
      </main>
      {!hedef && !staff ? (
        <>
          <nav
            className={cn(
              "fixed bottom-0 left-1/2 z-40 flex max-w-[calc(100vw-1.5rem)] -translate-x-1/2 gap-0.5 overflow-x-auto rounded-full border border-zinc-200 bg-white p-1 shadow-lg dark:border-zinc-800 dark:bg-zinc-950",
              "mb-[max(0.75rem,env(safe-area-inset-bottom))]",
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
                    "shrink-0 rounded-full p-2 transition sm:p-2.5",
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
