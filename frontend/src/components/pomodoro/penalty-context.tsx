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
import {
  answerPenalty,
  applyPenalty,
  getPenaltyStatus,
  clearPenalty,
  type TrapItem,
} from "@/lib/api";
import { getUserId } from "@/lib/user";

type PenaltyContextValue = {
  isPenalized: boolean;
  streak: number;
  needed: number;
  trap: TrapItem | null;
  message: string;
  busy: boolean;
  applyFocusPenalty: (elapsedSeconds: number) => Promise<void>;
  submitAnswer: (chosen: string) => Promise<void>;
  refresh: () => Promise<void>;
};

const PenaltyContext = createContext<PenaltyContextValue | null>(null);

export function PenaltyProvider({ children }: { children: ReactNode }) {
  const [isPenalized, setIsPenalized] = useState(false);
  const [streak, setStreak] = useState(0);
  const [needed, setNeeded] = useState(3);
  const [trap, setTrap] = useState<TrapItem | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const status = await getPenaltyStatus(getUserId());
      setIsPenalized(status.is_penalized);
      setStreak(status.penalty_clear_count);
      setNeeded(status.needed);
      setTrap(status.trap);
    } catch {
      /* backend kapalıysa kilit açılmasın diye sessiz geç */
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const applyFocusPenalty = useCallback(async (elapsedSeconds: number) => {
    setBusy(true);
    try {
      const status = await applyPenalty(getUserId(), elapsedSeconds);
      setIsPenalized(true);
      setStreak(0);
      setNeeded(status.needed);
      setTrap(status.trap);
      setMessage(status.message || "Odak bozuldu.");
    } catch (err) {
      setMessage(
        err instanceof Error ? err.message : "Ceza uygulanamadı. Bağlantıyı kontrol et.",
      );
    } finally {
      setBusy(false);
    }
  }, []);

  const submitAnswer = useCallback(async (chosen: string) => {
    if (!trap) return;
    setBusy(true);
    try {
      const result = await answerPenalty({
        user_id: getUserId(),
        trap_id: trap.id,
        chosen,
      });
      setMessage(result.message);
      setStreak(result.streak);
      setNeeded(result.needed);
      setIsPenalized(result.is_penalized);
      setTrap(result.trap);
      if (result.unlocked) {
        await clearPenalty(getUserId()).catch(() => undefined);
        setIsPenalized(false);
        setStreak(0);
        setTrap(null);
      }
    } catch (err) {
      setMessage(
        err instanceof Error ? err.message : "Cevap gönderilemedi.",
      );
    } finally {
      setBusy(false);
    }
  }, [trap]);

  const value = useMemo(
    () => ({
      isPenalized,
      streak,
      needed,
      trap,
      message,
      busy,
      applyFocusPenalty,
      submitAnswer,
      refresh,
    }),
    [
      isPenalized,
      streak,
      needed,
      trap,
      message,
      busy,
      applyFocusPenalty,
      submitAnswer,
      refresh,
    ],
  );

  return (
    <PenaltyContext.Provider value={value}>{children}</PenaltyContext.Provider>
  );
}

export function usePenalty() {
  const ctx = useContext(PenaltyContext);
  if (!ctx) {
    throw new Error("usePenalty PenaltyProvider içinde kullanılmalı.");
  }
  return ctx;
}
