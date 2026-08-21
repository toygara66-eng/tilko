"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { cn } from "@/lib/utils";

const STORAGE_KEY = "kpss_handwritten_mode_v2";

type NoteModeContextValue = {
  isHandwrittenMode: boolean;
  setIsHandwrittenMode: (value: boolean) => void;
};

const NoteModeContext = createContext<NoteModeContextValue | null>(null);

export function NoteModeProvider({ children }: { children: ReactNode }) {
  const [isHandwrittenMode, setIsHandwrittenMode] = useState(true);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === "0") setIsHandwrittenMode(false);
    if (stored === "1") setIsHandwrittenMode(true);
    setReady(true);
  }, []);

  useEffect(() => {
    if (!ready) return;
    window.localStorage.setItem(STORAGE_KEY, isHandwrittenMode ? "1" : "0");
  }, [isHandwrittenMode, ready]);

  return (
    <NoteModeContext.Provider
      value={{ isHandwrittenMode, setIsHandwrittenMode }}
    >
      {children}
    </NoteModeContext.Provider>
  );
}

export function useNoteMode() {
  const ctx = useContext(NoteModeContext);
  const [local, setLocal] = useState(true);
  if (ctx) return ctx;
  return { isHandwrittenMode: local, setIsHandwrittenMode: setLocal };
}

export function NoteModeToggle({ className }: { className?: string }) {
  const { isHandwrittenMode, setIsHandwrittenMode } = useNoteMode();

  return (
    <button
      type="button"
      role="switch"
      aria-checked={isHandwrittenMode}
      aria-label={isHandwrittenMode ? "Defter modu açık" : "Odak modu açık"}
      onClick={() => setIsHandwrittenMode(!isHandwrittenMode)}
      className={cn(
        "inline-flex items-center gap-3 rounded-full border px-3 py-1.5 text-sm shadow-lg backdrop-blur-md transition",
        "border-zinc-200 bg-white text-zinc-800 hover:border-zinc-400",
        "dark:border-zinc-800 dark:bg-zinc-900/90 dark:text-zinc-200 dark:hover:border-zinc-600",
        className,
      )}
    >
      <span className="whitespace-nowrap font-medium">
        {isHandwrittenMode ? "📝 Defter Modu" : "📖 Odak Modu"}
      </span>
      <span
        className={cn(
          "relative h-6 w-11 rounded-full transition-colors",
          isHandwrittenMode ? "bg-amber-400" : "bg-cyan-400",
        )}
      >
        <span
          className={cn(
            "absolute top-0.5 h-5 w-5 rounded-full bg-zinc-950 shadow transition-transform",
            isHandwrittenMode ? "left-0.5" : "left-0.5 translate-x-5",
          )}
        />
      </span>
    </button>
  );
}
