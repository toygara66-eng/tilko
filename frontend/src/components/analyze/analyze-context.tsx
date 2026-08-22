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
import { analyzeVideo, getAnalyzeJob, type AnalyzeResponse } from "@/lib/api";
import {
  fetchCaptionsForVideo,
  parseTranscriptPaste,
} from "@/lib/captions";
import { getUserId } from "@/lib/user";
import { useProfile } from "@/components/profile/profile-context";

const STORAGE_KEY = "tilko_last_analyze";

export type AnalyzeStartInput = {
  video_url: string;
  subject?: string;
  question_count: number;
  ad_watched?: boolean;
  subject_type?: string;
  is_yks_fen_question?: boolean;
  transcript_text?: string;
};

type StoredAnalyze = {
  result: AnalyzeResponse;
  url: string;
  subject: string;
  savedAt: number;
};

type AnalyzeContextValue = {
  result: AnalyzeResponse | null;
  url: string;
  subject: string;
  busy: boolean;
  elapsed: number;
  error: string;
  panelOpen: boolean;
  setPanelOpen: (open: boolean) => void;
  startAnalyze: (input: AnalyzeStartInput) => Promise<void>;
};

const AnalyzeContext = createContext<AnalyzeContextValue | null>(null);

function readStored(): StoredAnalyze | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as StoredAnalyze;
    if (!parsed?.result?.notes) return null;
    return parsed;
  } catch {
    return null;
  }
}

function writeStored(payload: StoredAnalyze) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
  } catch {
    /* kota / gizli mod */
  }
}

function stillRunning(data: AnalyzeResponse) {
  return Boolean(data.job_id) && (data.job_status || "done") === "running";
}

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

export function AnalyzeProvider({ children }: { children: ReactNode }) {
  const { apply, refresh } = useProfile();
  const [result, setResult] = useState<AnalyzeResponse | null>(null);
  const [url, setUrl] = useState("");
  const [subject, setSubject] = useState("");
  const [busy, setBusy] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState("");
  const [panelOpen, setPanelOpen] = useState(false);
  const job = useRef(0);
  const busyRef = useRef(false);
  const resumed = useRef(false);

  const remember = useCallback(
    (data: AnalyzeResponse, videoUrl: string, topic: string) => {
      setResult(data);
      writeStored({
        result: data,
        url: videoUrl,
        subject: topic,
        savedAt: Date.now(),
      });
      apply({
        aiCreditsLeft: data.ai_credits_left,
        aiCreditLimit: data.ai_credit_limit,
        isPremium: data.is_premium,
        isInTrial: data.is_in_trial_period,
        isAdTier: data.is_ad_tier,
        dailyAdCredits: data.daily_ad_credits,
        dailyAdLimit: data.daily_ad_limit,
        trialDaysLeft: data.trial_days_left,
      });
    },
    [apply],
  );

  const pollUntilDone = useCallback(
    async (jobId: string, token: number, videoUrl: string, topic: string) => {
      while (token === job.current) {
        await sleep(2500);
        if (token !== job.current) return;
        try {
          const next = await getAnalyzeJob(jobId);
          if (token !== job.current) return;
          if ((next.job_status || "") === "error") {
            setError(
              next.job_error ||
                "YouTube altyazısı alınamadı. Videoda altyazı (otomatik de olur) açık olsun.",
            );
            void refresh();
            return;
          }
          remember(next, videoUrl, topic);
          if (!stillRunning(next)) return;
        } catch {
          const saved = readStored();
          if (saved?.result?.job_id === jobId) {
            remember(
              { ...saved.result, job_status: "done" },
              videoUrl,
              topic,
            );
          }
          return;
        }
      }
    },
    [remember, refresh],
  );

  useEffect(() => {
    const saved = readStored();
    if (!saved) return;
    setResult(saved.result);
    setUrl(saved.url);
    setSubject(saved.subject);
    if (resumed.current) return;
    resumed.current = true;
    if (!stillRunning(saved.result) || !saved.result.job_id) return;
    const token = ++job.current;
    busyRef.current = true;
    setBusy(true);
    setPanelOpen(true);
    void pollUntilDone(saved.result.job_id, token, saved.url, saved.subject).finally(
      () => {
        if (token === job.current) {
          busyRef.current = false;
          setBusy(false);
        }
      },
    );
  }, [pollUntilDone]);

  useEffect(() => {
    if (!busy) {
      setElapsed(0);
      return;
    }
    const started = Date.now();
    const id = window.setInterval(() => {
      setElapsed(Math.floor((Date.now() - started) / 1000));
    }, 250);
    return () => window.clearInterval(id);
  }, [busy]);

  const startAnalyze = useCallback(
    async (input: AnalyzeStartInput) => {
      if (busyRef.current) return;
      const token = ++job.current;
      busyRef.current = true;
      setBusy(true);
      setError("");
      setUrl(input.video_url);
      setSubject(input.subject || "");
      const topic = input.subject || "";
      try {
        let transcript_lines = parseTranscriptPaste(input.transcript_text || "");
        if (transcript_lines.length < 3) {
          transcript_lines = await fetchCaptionsForVideo(input.video_url);
        }
        const data = await analyzeVideo({
          video_url: input.video_url,
          user_id: getUserId(),
          subject: input.subject,
          question_count: input.question_count,
          ad_watched: input.ad_watched,
          subject_type: input.subject_type,
          is_yks_fen_question: input.is_yks_fen_question,
          transcript_lines:
            transcript_lines.length >= 3 ? transcript_lines : undefined,
        });
        if (token !== job.current) return;
        remember(data, input.video_url, topic);
        setPanelOpen(true);
        void refresh();
        if (stillRunning(data) && data.job_id) {
          await pollUntilDone(data.job_id, token, input.video_url, topic);
        }
      } catch (err) {
        if (token !== job.current) return;
        setError(err instanceof Error ? err.message : "Analiz başarısız");
        void refresh();
      } finally {
        if (token === job.current) {
          busyRef.current = false;
          setBusy(false);
        }
      }
    },
    [pollUntilDone, refresh, remember],
  );

  const value = useMemo(
    () => ({
      result,
      url,
      subject,
      busy,
      elapsed,
      error,
      panelOpen,
      setPanelOpen,
      startAnalyze,
    }),
    [result, url, subject, busy, elapsed, error, panelOpen, startAnalyze],
  );

  return (
    <AnalyzeContext.Provider value={value}>{children}</AnalyzeContext.Provider>
  );
}

export function useAnalyze() {
  const ctx = useContext(AnalyzeContext);
  if (!ctx) throw new Error("useAnalyze AnalyzeProvider içinde kullanılmalı.");
  return ctx;
}
