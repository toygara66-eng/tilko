"use client";

import type { CSSProperties, ReactNode } from "react";
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

/** Play / APK sürüm damgası — telefonda hangi build olduğunu görmek için. */
export const APP_BUILD_LABEL = "1.0.13";

const NAV = [
  { href: "/", label: "Av", icon: LayoutDashboard },
  { href: "/tuzak-defteri", label: "Defter", icon: BookMarked },
  { href: "/gunluk-gorevler", label: "Görev", icon: Flame },
  { href: "/analiz", label: "Analiz", icon: Youtube },
  { href: "/notlarim", label: "Notlar", icon: StickyNote },
  { href: "/profil", label: "Profil", icon: UserRound },
];

const shellStyle: CSSProperties = {
  display: "flex",
  flexDirection: "column",
  height: "100dvh",
  maxHeight: "100dvh",
  width: "100%",
  overflow: "hidden",
  background: "#09090b",
  color: "#fafafa",
};

const headerStyle: CSSProperties = {
  flexShrink: 0,
  zIndex: 20,
  borderBottom: "3px solid #f97316",
  background: "#18181b",
  paddingTop: "env(safe-area-inset-top, 0px)",
};

const navWrapStyle: CSSProperties = {
  flexShrink: 0,
  zIndex: 20,
  display: "flex",
  justifyContent: "center",
  padding: "8px 12px",
  paddingBottom: "max(8px, env(safe-area-inset-bottom, 0px))",
  background: "#09090b",
  borderTop: "1px solid #3f3f46",
};

const navBarStyle: CSSProperties = {
  display: "flex",
  gap: 2,
  maxWidth: "100%",
  overflowX: "auto",
  borderRadius: 9999,
  border: "2px solid #f97316",
  background: "#18181b",
  padding: 4,
};

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
  const showNav = !hedef && !staff && !focused;

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

  if (!authOk && !isAuthPublicPath(path)) {
    return (
      <div
        style={{
          ...shellStyle,
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <Loader2 className="h-6 w-6 animate-spin text-orange-500" />
        <p style={{ marginTop: 12, fontSize: 12, color: "#a1a1aa" }}>
          TİLKO {APP_BUILD_LABEL}
        </p>
      </div>
    );
  }

  return (
    <div style={shellStyle}>
      {!hideChrome ? (
        <header style={headerStyle}>
          {hoca ? null : <VictoryStrip />}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              padding: "8px 12px",
              maxWidth: 1024,
              margin: "0 auto",
              width: "100%",
              boxSizing: "border-box",
            }}
          >
            <Link
              href={hoca ? "/hoca" : "/"}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                minWidth: 0,
                textDecoration: "none",
              }}
            >
              <TilkoLogo size={28} className="shrink-0" />
              <span
                style={{
                  fontSize: 14,
                  fontWeight: 800,
                  letterSpacing: "-0.02em",
                  color: "#fb923c",
                }}
              >
                TİLKO
              </span>
              <span
                style={{
                  fontSize: 10,
                  fontWeight: 600,
                  color: "#a1a1aa",
                  marginLeft: 2,
                }}
              >
                {APP_BUILD_LABEL}
              </span>
            </Link>
            {hoca ? (
              <span className="hidden text-xs font-medium text-zinc-500 sm:inline">
                Hoca paneli
              </span>
            ) : (
              <Link
                href="/profil"
                className="hidden min-w-0 truncate rounded-full border border-orange-400/40 bg-orange-500/10 px-2.5 py-1 text-[11px] font-medium text-orange-200 sm:inline-flex"
              >
                {profile.xp} XP
              </Link>
            )}
            <div
              style={{
                marginLeft: "auto",
                display: "flex",
                alignItems: "center",
                gap: 2,
                flexShrink: 0,
              }}
            >
              {hoca ? null : signedIn ? (
                <button
                  type="button"
                  onClick={() => {
                    logout();
                    hardNavigate("/giris");
                  }}
                  className="inline-flex items-center gap-1 rounded-full p-2 text-xs font-medium text-zinc-400"
                  title="Çıkış yap"
                >
                  <LogOut className="h-3.5 w-3.5" />
                </button>
              ) : (
                <Link
                  href="/giris"
                  style={{
                    padding: "6px 10px",
                    fontSize: 12,
                    color: "#d4d4d8",
                    textDecoration: "none",
                  }}
                >
                  Giriş
                </Link>
              )}
              {hoca ? null : <NoteModeToggle compact />}
              <ThemeToggle className="h-9 w-9 shrink-0 px-0 shadow-none" />
              {hoca ? null : <FeedbackHeaderButton />}
              <button
                type="button"
                onClick={() => setBoardOpen(true)}
                aria-label="Kurnazlar Listesi"
                className="shrink-0 rounded-full p-2 text-orange-500"
                hidden={hoca}
              >
                <Trophy className="h-5 w-5" />
              </button>
            </div>
          </div>
        </header>
      ) : null}

      <main
        style={{
          flex: 1,
          minHeight: 0,
          overflowX: "hidden",
          overflowY: "auto",
          WebkitOverflowScrolling: "touch",
          background: hideChrome ? undefined : "#09090b",
        }}
        className={cn(
          "relative mx-auto w-full min-w-0 max-w-full",
          hideChrome
            ? "max-w-none p-0"
            : hoca
              ? "max-w-5xl px-3 py-6 sm:px-4 md:px-8"
              : home || focused
                ? "flex max-w-xl flex-col justify-start px-3 py-4 sm:px-4"
                : "max-w-5xl px-3 py-6 sm:px-4 md:px-8",
        )}
      >
        {children}
      </main>

      {showNav ? (
        <nav style={navWrapStyle} aria-label="Ana menü">
          <div style={navBarStyle}>
            {NAV.map((item) => {
              const active = path === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-label={item.label}
                  title={item.label}
                  style={{
                    flexShrink: 0,
                    borderRadius: 9999,
                    padding: 10,
                    background: active ? "#f97316" : "transparent",
                    color: active ? "#09090b" : "#a1a1aa",
                    display: "inline-flex",
                  }}
                >
                  <item.icon className="h-4 w-4" />
                </Link>
              );
            })}
          </div>
        </nav>
      ) : null}

      {!hedef && !staff ? (
        <KurnazModal open={boardOpen} onClose={() => setBoardOpen(false)} />
      ) : null}
    </div>
  );
}
