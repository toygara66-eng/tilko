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
import { usePathname, useRouter } from "next/navigation";
import { analyzeVideo, getAnalyzeJob, cancelAnalyzeJob, wakeApi, humanizeNetworkError, type AnalyzeResponse } from "@/lib/api";
import {
  fetchCaptionsForVideo,
  parseTranscriptPaste,
  extractYoutubeId,
} from "@/lib/captions";
import { getUserId } from "@/lib/user";
import { useProfile } from "@/components/profile/profile-context";

const STORAGE_KEY = "tilko_last_analyze";
const STORAGE_KEY_LEGACY = "tilko_last_analyze"; // eski anahtar da silinsin
const NOTEBOOK_BUMP_KEY = "tilko_notebook_bump";
/** Yarım running kayıtlarını bir kez temizle (eski auto-resume). */
const CLEAR_STALE_FLAG = "tilko_cleared_stale_analyze_v2";

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
  cancelAnalyze: () => void;
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

function bumpNotebook() {
  try {
    window.localStorage.setItem(NOTEBOOK_BUMP_KEY, String(Date.now()));
    window.dispatchEvent(new Event("tilko-notebook-bump"));
  } catch {
    /* ignore */
  }
}

function stillRunning(data: AnalyzeResponse) {
  return Boolean(data.job_id) && (data.job_status || "done") === "running";
}

/** Render in-memory job kayboldu / 404. */
function isMissingJobError(err: unknown): boolean {
  const message =
    err instanceof Error
      ? err.message
      : typeof err === "string"
        ? err
        : String(err ?? "");
  return /404|bulunamad|not found|işi bulunamad/i.test(message);
}

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

/** Kayıttaki yarım job'ı temizle — sayfa açılışında poll/busy yok. */
function settleStored(saved: StoredAnalyze): AnalyzeResponse | null {
  const notes = saved.result?.notes || [];
  if (!notes.length) {
    try {
      window.localStorage.removeItem(STORAGE_KEY);
    } catch {
      /* ignore */
    }
    return null;
  }
  const settled: AnalyzeResponse = {
    ...saved.result,
    job_id: undefined,
    job_status: "done",
    job_error: undefined,
  };
  writeStored({
    result: settled,
    url: saved.url,
    subject: saved.subject,
    savedAt: Date.now(),
  });
  return settled;
}

/** Kayıttan gelen cevapta da kısa “hazırlanıyor” hissi kalsın. */
async function holdPreparing(startedAt: number, cached: boolean) {
  const minMs = cached ? 1100 : 0;
  const wait = Math.max(0, minMs - (Date.now() - startedAt));
  if (wait > 0) await sleep(wait);
}

export function AnalyzeProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
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
  const lastDoneVideo = useRef("");
  const activeJobId = useRef("");
  const pathRef = useRef(pathname);
  pathRef.current = pathname;

  const goNotebook = useCallback(
    (data: AnalyzeResponse, videoUrl: string) => {
      if ((data.notes?.length || 0) === 0 || stillRunning(data)) return;
      bumpNotebook();
      const vid =
        (data.video_id || "").trim() || extractYoutubeId(videoUrl) || "";
      // Aynı video tekrar: paneli açma, Notlarım'a zorla gitme.
      if (vid && vid === lastDoneVideo.current) {
        setPanelOpen(false);
        return;
      }
      if (vid) lastDoneVideo.current = vid;
      setPanelOpen(false);
      if (pathRef.current === "/analiz") {
        router.push("/notlarim");
      }
    },
    [router],
  );

  const remember = useCallback(
    (data: AnalyzeResponse, videoUrl: string, topic: string) => {
      if (data.job_id && stillRunning(data)) {
        activeJobId.current = data.job_id;
      } else {
        activeJobId.current = "";
      }
      setResult(data);
      // Running job'ı asla kaydetme — F5 / siteye girişte arka plan poll olmasın.
      if (stillRunning(data)) {
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
        return;
      }
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
      let fails = 0;
      const started = Date.now();
      while (token === job.current) {
        await sleep(Math.min(2000 + fails * 800, 6000));
        if (token !== job.current) return;
        // 12 dk: Gemini + yedek sağlayıcı zinciri için yeterli.
        if (Date.now() - started > 12 * 60_000) {
          setError(
            "Analiz uzun sürdü. Sayfayı yenilemeden 20 sn bekle, bir kez daha dene.",
          );
          void refresh();
          return;
        }
        try {
          const next = await getAnalyzeJob(jobId);
          if (token !== job.current) return;
          fails = 0;
          if ((next.job_status || "") === "error") {
            setError(
              humanizeNetworkError(
                next.job_error ||
                  "YouTube altyazısı alınamadı. Videoda altyazı (otomatik de olur) açık olsun.",
              ),
            );
            void refresh();
            return;
          }
          remember(next, videoUrl, topic);
          if (!stillRunning(next)) {
            goNotebook(next, videoUrl);
            return;
          }
        } catch (err) {
          fails += 1;
          // Job Render yeniden başlayınca silinir — 100 sn boş dönme.
          if (isMissingJobError(err) || fails >= 30) {
            setError(
              isMissingJobError(err)
                ? "Önceki analiz sunucuda kalmamış (yeniden başlama). Linki tekrar Analiz et."
                : humanizeNetworkError(
                    err,
                    "Analiz durumu alınamadı. Biraz bekleyip tekrar dene.",
                  ),
            );
            void refresh();
            return;
          }
        }
      }
    },
    [remember, refresh, goNotebook],
  );

  useEffect(() => {
    if (resumed.current) return;
    resumed.current = true;

    // Eski auto-resume kalıntısı: running kaydı + eski anahtarları temizle.
    try {
      if (!window.localStorage.getItem(CLEAR_STALE_FLAG)) {
        window.localStorage.removeItem(STORAGE_KEY);
        window.localStorage.removeItem(STORAGE_KEY_LEGACY);
        window.localStorage.setItem(CLEAR_STALE_FLAG, "1");
        return;
      }
    } catch {
      /* ignore */
    }

    const saved = readStored();
    if (!saved) return;

    // Sayfa açılışında asla poll / busy / wake yok.
    if (stillRunning(saved.result) || !(saved.result.notes?.length || 0)) {
      settleStored(saved);
      return;
    }

    setResult(saved.result);
    setUrl(saved.url || "");
    setSubject(saved.subject || "");
    const vid =
      (saved.result.video_id || "").trim() ||
      extractYoutubeId(saved.url) ||
      "";
    if (vid) lastDoneVideo.current = vid;
  }, []);

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
      const nextId = extractYoutubeId(input.video_url);
      const sameVideo =
        Boolean(nextId) &&
        (nextId === lastDoneVideo.current ||
          nextId === extractYoutubeId(url) ||
          nextId === (result?.video_id || ""));
      const alreadyReady =
        sameVideo &&
        (result?.notes?.length || 0) > 0 &&
        !stillRunning(result!);

      setError("");
      setUrl(input.video_url);
      setSubject(input.subject || "");
      setPanelOpen(false);

      // Aynı link + hazır not varsa paneli/busy'yi hiç açma.
      if (alreadyReady) {
        lastDoneVideo.current = nextId;
        void (async () => {
          try {
            await wakeApi();
            const data = await analyzeVideo({
              video_url: input.video_url,
              user_id: getUserId(),
              subject: input.subject,
              question_count: input.question_count,
              ad_watched: input.ad_watched,
              subject_type: input.subject_type,
              is_yks_fen_question: input.is_yks_fen_question,
            });
            if (data.notes?.length) {
              remember(data, input.video_url, input.subject || "");
              void refresh();
            }
          } catch {
            /* yereldeki not kalsın */
          }
        })();
        return;
      }

      const token = ++job.current;
      const startedAt = Date.now();
      activeJobId.current = "";
      busyRef.current = true;
      setBusy(true);
      if (!sameVideo) {
        setResult(null);
      }
      const topic = input.subject || "";
      const pasted = parseTranscriptPaste(input.transcript_text || "");

      const run = (transcript_lines?: { start: number; text: string }[]) =>
        analyzeVideo({
          video_url: input.video_url,
          user_id: getUserId(),
          subject: input.subject,
          question_count: input.question_count,
          ad_watched: input.ad_watched,
          subject_type: input.subject_type,
          is_yks_fen_question: input.is_yks_fen_question,
          transcript_lines:
            transcript_lines && transcript_lines.length >= 3
              ? transcript_lines
              : undefined,
        });

      try {
        await wakeApi();
        if (token !== job.current) return;

        let captions =
          pasted.length >= 3
            ? pasted
            : ([] as { start: number; text: string }[]);
        // Altyazıyı önce telefonda/tarayıcıda çek; sunucu OpenRouter'a düşmesin.
        if (captions.length < 3) {
          try {
            captions = await fetchCaptionsForVideo(input.video_url);
          } catch {
            captions = [];
          }
        }
        if (token !== job.current) return;

        let data = await run(
          captions.length >= 3 ? captions : undefined,
        );
        if (token !== job.current) return;

        const emptyFresh =
          !data.cached &&
          !(data.notes?.length || data.questions?.length) &&
          !stillRunning(data) &&
          captions.length < 3;

        if (emptyFresh) {
          const retry = await fetchCaptionsForVideo(input.video_url);
          if (token !== job.current) return;
          if (retry.length >= 3) {
            data = await run(retry);
            if (token !== job.current) return;
          }
        }

        if (!(data.cached || sameVideo)) {
          await holdPreparing(startedAt, false);
        }
        if (token !== job.current) return;
        remember(data, input.video_url, topic);
        void refresh();
        if (stillRunning(data) && data.job_id) {
          await pollUntilDone(data.job_id, token, input.video_url, topic);
        } else {
          goNotebook(data, input.video_url);
        }
      } catch (err) {
        if (token !== job.current) return;
        const msg = err instanceof Error ? err.message : "Analiz başarısız";
        if (pasted.length < 3 && /altyazı|transkript|subtitle|openrouter|kredi/i.test(msg)) {
          try {
            const captions = await fetchCaptionsForVideo(input.video_url);
            if (token !== job.current) return;
            if (captions.length >= 3) {
              const data = await run(captions);
              if (token !== job.current) return;
              if (!(data.cached || sameVideo)) {
                await holdPreparing(startedAt, false);
              }
              if (token !== job.current) return;
              remember(data, input.video_url, topic);
              void refresh();
              if (stillRunning(data) && data.job_id) {
                await pollUntilDone(data.job_id, token, input.video_url, topic);
              } else {
                goNotebook(data, input.video_url);
              }
              return;
            }
          } catch {
            /* aşağıda orijinal hata */
          }
        }
        setError(humanizeNetworkError(err, "Analiz başarısız"));
        void refresh();
      } finally {
        if (token === job.current) {
          busyRef.current = false;
          setBusy(false);
        }
      }
    },
    [pollUntilDone, refresh, remember, goNotebook, url, result],
  );

  const cancelAnalyze = useCallback(() => {
    if (!busyRef.current) return;
    const jobId = activeJobId.current || result?.job_id || "";
    job.current += 1;
    activeJobId.current = "";
    busyRef.current = false;
    setBusy(false);
    setElapsed(0);
    setError("Analiz iptal edildi. Yeni linkle Analiz et.");
    setResult((prev) => {
      const hasNotes = (prev?.notes?.length || 0) > 0;
      if (!prev || !hasNotes) {
        try {
          window.localStorage.removeItem(STORAGE_KEY);
        } catch {
          /* ignore */
        }
        return null;
      }
      const settled = {
        ...prev,
        job_id: undefined,
        job_status: "done" as const,
      };
      writeStored({
        result: settled,
        url,
        subject,
        savedAt: Date.now(),
      });
      return settled;
    });
    if (jobId) {
      void cancelAnalyzeJob(jobId).catch(() => {
        /* istemci zaten durdu */
      });
    }
  }, [result?.job_id, url, subject]);

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
      cancelAnalyze,
    }),
    [
      result,
      url,
      subject,
      busy,
      elapsed,
      error,
      panelOpen,
      startAnalyze,
      cancelAnalyze,
    ],
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
