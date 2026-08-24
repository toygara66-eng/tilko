"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { cn } from "@/lib/utils";

const STORAGE_KEY = "kpss_handwritten_mode_v2";

type NoteModeContextValue = {
  isHandwrittenMode: boolean;
  setIsHandwrittenMode: (value: boolean) => void;
  toggleNoteMode: () => void;
};

const NoteModeContext = createContext<NoteModeContextValue | null>(null);

function readStoredMode(): boolean {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === "0") return false;
    if (stored === "1") return true;
  } catch {
    /* ignore */
  }
  return true;
}

export function NoteModeProvider({ children }: { children: ReactNode }) {
  // null = henüz localStorage okunmadı (SSR / ilk boyama)
  const [isHandwrittenMode, setMode] = useState<boolean | null>(null);

  useEffect(() => {
    setMode(readStoredMode());
  }, []);

  useEffect(() => {
    if (isHandwrittenMode === null) return;
    try {
      window.localStorage.setItem(STORAGE_KEY, isHandwrittenMode ? "1" : "0");
    } catch {
      /* ignore */
    }
  }, [isHandwrittenMode]);

  useEffect(() => {
    const onStorage = (event: StorageEvent) => {
      if (event.key !== STORAGE_KEY) return;
      setMode(event.newValue === "0" ? false : true);
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  const setIsHandwrittenMode = useCallback((value: boolean) => {
    setMode(Boolean(value));
  }, []);

  const toggleNoteMode = useCallback(() => {
    setMode((prev) => !(prev ?? true));
  }, []);

  const value = useMemo(
    () => ({
      // İlk boyamada defter varsayılan (layout kayması olmasın)
      isHandwrittenMode: isHandwrittenMode ?? true,
      setIsHandwrittenMode,
      toggleNoteMode,
    }),
    [isHandwrittenMode, setIsHandwrittenMode, toggleNoteMode],
  );

  return (
    <NoteModeContext.Provider value={value}>{children}</NoteModeContext.Provider>
  );
}

export function useNoteMode() {
  const ctx = useContext(NoteModeContext);
  if (!ctx) {
    throw new Error("useNoteMode NoteModeProvider içinde kullanılmalı");
  }
  return ctx;
}

export function NoteModeToggle({
  className,
  compact = false,
}: {
  className?: string;
  compact?: boolean;
}) {
  const { isHandwrittenMode, toggleNoteMode } = useNoteMode();

  return (
    <button
      type="button"
      role="switch"
      aria-checked={isHandwrittenMode}
      aria-label={isHandwrittenMode ? "Defter modu açık" : "Odak modu açık"}
      title={
        isHandwrittenMode
          ? "Defter modu: el yazısı not kağıdı. Odak için dokun."
          : "Odak modu: sade okuma. Defter için dokun."
      }
      onClick={(event) => {
        event.preventDefault();
        event.stopPropagation();
        toggleNoteMode();
      }}
      className={cn(
        "inline-flex shrink-0 items-center gap-2 rounded-full border px-2.5 py-1.5 text-xs font-medium shadow-md backdrop-blur-md transition active:scale-[0.98] sm:gap-3 sm:px-3 sm:text-sm",
        isHandwrittenMode
          ? "border-amber-400/60 bg-amber-100 text-amber-950 hover:bg-amber-200 dark:border-amber-500/50 dark:bg-amber-950/70 dark:text-amber-100"
          : "border-cyan-400/60 bg-cyan-100 text-cyan-950 hover:bg-cyan-200 dark:border-cyan-500/50 dark:bg-cyan-950/70 dark:text-cyan-100",
        className,
      )}
    >
      <span className="whitespace-nowrap">
        {isHandwrittenMode ? "📝 Defter" : "📖 Odak"}
        {compact ? null : <span className="hidden sm:inline"> Modu</span>}
      </span>
      <span
        className={cn(
          "relative h-5 w-9 rounded-full transition-colors sm:h-6 sm:w-11",
          isHandwrittenMode ? "bg-amber-500" : "bg-cyan-500",
        )}
      >
        <span
          className={cn(
            "absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform sm:h-5 sm:w-5",
            isHandwrittenMode
              ? "left-0.5"
              : "left-0.5 translate-x-4 sm:translate-x-5",
          )}
        />
      </span>
    </button>
  );
}
