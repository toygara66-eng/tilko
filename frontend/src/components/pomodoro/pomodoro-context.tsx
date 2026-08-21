"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { usePenalty } from "@/components/pomodoro/penalty-context";
import { completePomodoro } from "@/lib/api";
import { getUserId } from "@/lib/user";
import { useProfile } from "@/components/profile/profile-context";

type PomodoroContextValue = {
  duration: number;
  remaining: number;
  running: boolean;
  done: boolean;
  start: () => void;
  pause: () => void;
  choose: (seconds: number) => void;
};

const PomodoroContext = createContext<PomodoroContextValue | null>(null);

export function PomodoroProvider({ children }: { children: ReactNode }) {
  const { isPenalized, applyFocusPenalty } = usePenalty();
  const { apply } = useProfile();
  const [duration, setDuration] = useState(25 * 60);
  const [remaining, setRemaining] = useState(25 * 60);
  const [running, setRunning] = useState(false);
  const [done, setDone] = useState(false);
  const runningRef = useRef(false);
  const remainingRef = useRef(25 * 60);
  const punishingRef = useRef(false);
  const isPenalizedRef = useRef(isPenalized);
  const sessionId = useRef("");

  useEffect(() => {
    runningRef.current = running;
  }, [running]);

  useEffect(() => {
    remainingRef.current = remaining;
  }, [remaining]);

  useEffect(() => {
    isPenalizedRef.current = isPenalized;
    if (isPenalized) {
      setRunning(false);
      runningRef.current = false;
    }
  }, [isPenalized]);

  const punish = useCallback(async () => {
    if (punishingRef.current || isPenalizedRef.current) return;
    if (!runningRef.current || remainingRef.current <= 0) return;
    punishingRef.current = true;
    const elapsed = duration - remainingRef.current;
    setRunning(false);
    runningRef.current = false;
    try {
      await applyFocusPenalty(Math.max(elapsed, 0));
    } catch {
      /* ceza API düşse bile sayfa çökmesin */
    } finally {
      punishingRef.current = false;
    }
  }, [applyFocusPenalty, duration]);

  useEffect(() => {
    if (!running) return;
    const id = window.setInterval(() => {
      setRemaining((prev) => {
        if (prev <= 1) {
          window.clearInterval(id);
          setRunning(false);
          setDone(true);
          runningRef.current = false;
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => window.clearInterval(id);
  }, [running]);

  useEffect(() => {
    const onVisibility = () => {
      if (document.hidden || document.visibilityState === "hidden") {
        void punish();
      }
    };
    const onPageHide = () => {
      void punish();
    };
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("pagehide", onPageHide);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("pagehide", onPageHide);
    };
  }, [punish]);

  useEffect(() => {
    if (!done || !sessionId.current) return;
    const token = sessionId.current;
    void completePomodoro(getUserId(), token)
      .then((data) => {
        apply({
          xp: data.xp,
          title: data.title,
          titleEmoji: data.title_emoji,
          level: data.level,
        });
      })
      .catch(() => undefined);
  }, [done, apply]);

  const start = useCallback(() => {
    if (isPenalizedRef.current) return;
    sessionId.current = crypto.randomUUID();
    setDone(false);
    setRemaining((prev) => (prev <= 0 ? duration : prev));
    setRunning(true);
  }, [duration]);

  const pause = useCallback(() => {
    setRunning(false);
  }, []);

  const choose = useCallback((seconds: number) => {
    setDuration(seconds);
    setRemaining(seconds);
    setDone(false);
    setRunning(false);
  }, []);

  const value = useMemo(
    () => ({ duration, remaining, running, done, start, pause, choose }),
    [duration, remaining, running, done, start, pause, choose],
  );

  return (
    <PomodoroContext.Provider value={value}>{children}</PomodoroContext.Provider>
  );
}

export function usePomodoro() {
  const ctx = useContext(PomodoroContext);
  if (!ctx) {
    throw new Error("usePomodoro PomodoroProvider içinde kullanılmalı.");
  }
  return ctx;
}
