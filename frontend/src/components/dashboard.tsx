"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { Loader2, Sparkles } from "lucide-react";
import { FenLab } from "@/components/yks/fen-lab";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { getUserId } from "@/lib/user";
import { extractYoutubeId } from "@/lib/captions";
import { isNumericalSubject, subjectsFor } from "@/lib/exams";
import { useProfile } from "@/components/profile/profile-context";
import { VideoRecs } from "@/components/diagnostic/video-recs";
import { AdWatchModal } from "@/components/ads/ad-watch-modal";
import { ProUpgradeButton } from "@/components/billing/pro-upgrade-button";
import { useAnalyze } from "@/components/analyze/analyze-context";
import { NotesPanel } from "@/components/analyze/notes-drawer";
import { unlockAd } from "@/lib/api";
import { cn } from "@/lib/utils";

export function Dashboard() {
  const { profile } = useProfile();
  const {
    result,
    busy,
    elapsed,
    error,
    startAnalyze,
    cancelAnalyze,
  } = useAnalyze();
  const [url, setUrl] = useState("");
  const [subject, setSubject] = useState("Vatandaşlık");
  const [subjectType, setSubjectType] = useState<"sozel" | "sayisal">("sozel");
  const [fenBranch, setFenBranch] = useState("");
  const [count, setCount] = useState(10);
  const [adOpen, setAdOpen] = useState(false);
  const [transcriptText, setTranscriptText] = useState("");
  const youtubeId = extractYoutubeId(url);
  const adTier = profile.isAdTier && !profile.isPremium;
  const outOfTrialCredits =
    !profile.isPremium && profile.isInTrial && profile.aiCreditsLeft <= 0;
  const outOfAdCredits = adTier && profile.dailyAdCredits <= 0;
  const isYks = profile.examTarget === "yks";
  const subjects = subjectsFor(profile.examTarget || "kpss_lisans");
  const isYksFen =
    isYks &&
    (Boolean(fenBranch) || /fizik|kimya|biyoloji|\bfen\b/i.test(subject));

  useEffect(() => {
    setFenBranch("");
    const first = subjectsFor(profile.examTarget || "kpss_lisans")[0] || "Tarih";
    setSubject(first);
    setSubjectType(isNumericalSubject(first) ? "sayisal" : "sozel");
  }, [profile.examTarget]);

  useEffect(() => {
    if (profile.weakTopics[0] && subjects.includes(profile.weakTopics[0])) {
      setSubject(profile.weakTopics[0]);
    }
  }, [profile.weakTopics, profile.examTarget]);

  function runAnalyze(adWatched: boolean) {
    void startAnalyze({
      video_url: url.trim(),
      subject: subject.trim() || undefined,
      question_count: count,
      ad_watched: adWatched,
      subject_type: subjectType,
      is_yks_fen_question: isYksFen,
      transcript_text: transcriptText,
    });
  }

  function onAnalyze(event: FormEvent) {
    event.preventDefault();
    if (outOfTrialCredits || outOfAdCredits) return;
    if (adTier) {
      setAdOpen(true);
      return;
    }
    runAnalyze(false);
  }

  async function afterAd() {
    setAdOpen(false);
    try {
      await unlockAd(getUserId());
    } catch {
      /* convert yine ad_watched gönderir */
    }
    runAnalyze(true);
  }

  return (
    <div className="space-y-10">
      <section className="space-y-3">
        <Badge>TİLKO</Badge>
        <h1 className="max-w-3xl text-3xl font-semibold tracking-tight text-zinc-900 dark:text-white md:text-5xl">
          Ders analiz et
        </h1>
        <p className="max-w-xl text-zinc-600 dark:text-zinc-400">
          YouTube linkini yapıştırıp Analiz et’e bas. Sayfa açılınca kendiliğinden
          başlamaz; yanlış linkte Durdur’a basabilirsin.
          {profile.weakTopics.length
            ? ` Şimdi ${profile.weakTopics.join(", ")} tarafını hedefle.`
            : ""}
        </p>
      </section>

      <Card className="border-cyan-400/20 p-3 shadow-neon md:p-5">
        <form onSubmit={onAnalyze} className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <label className="block text-xs font-medium uppercase tracking-[0.2em] text-zinc-500">
              Yeni YouTube linki analiz et
            </label>
            <p
              className={cn(
                "rounded-full border px-3 py-1 text-xs font-medium",
                profile.isPremium
                  ? "border-orange-400/50 bg-orange-500/10 text-orange-800 dark:text-orange-200"
                  : outOfTrialCredits || outOfAdCredits
                    ? "border-red-400/50 bg-red-500/10 text-red-700 dark:text-red-300"
                    : "border-orange-400/40 bg-orange-500/10 text-orange-800 dark:text-orange-200",
              )}
            >
              {profile.isPremium
                ? "Sınırsız · Tilko Pro"
                : adTier
                  ? `Bugünkü Reklamlı Çeviri Hakkın: ${profile.dailyAdCredits} / ${profile.dailyAdLimit}`
                  : `Kalan Video Hakkı: ${profile.aiCreditsLeft} / ${profile.aiCreditLimit}`}
            </p>
          </div>
          <Input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://www.youtube.com/watch?v=..."
            className="h-16 text-base md:text-lg"
            required
          />
          <details className="rounded-xl border border-zinc-200 bg-white/40 px-3 py-2 dark:border-zinc-800 dark:bg-zinc-900/40">
            <summary className="cursor-pointer text-sm text-zinc-600 dark:text-zinc-400">
              Altyazı gelmezse transkripti buraya yapıştır
            </summary>
            <p className="mt-2 text-xs text-zinc-500">
              YouTube → üç nokta → Transkripti göster, veya{" "}
              {youtubeId ? (
                <>
                  <a
                    href={`https://youtube-transcript.ai/transcript/${youtubeId}.txt?lang=tr`}
                    target="_blank"
                    rel="noreferrer"
                    className="text-orange-600 underline dark:text-orange-300"
                  >
                    youtube-transcript.ai
                  </a>
                  {" (düz metin) / "}
                  <a
                    href={`https://youtubetotranscript.com/transcript?v=${youtubeId}`}
                    target="_blank"
                    rel="noreferrer"
                    className="text-orange-600 underline dark:text-orange-300"
                  >
                    youtubetotranscript
                  </a>
                  {" / "}
                  <a
                    href={`https://www.youtube-transcript.io/videos?id=${youtubeId}`}
                    target="_blank"
                    rel="noreferrer"
                    className="text-orange-600 underline dark:text-orange-300"
                  >
                    youtube-transcript.io
                  </a>
                </>
              ) : (
                "youtube-transcript.ai / youtubetotranscript / youtube-transcript.io"
              )}
              , kopyala, yapıştır.
            </p>
            <textarea
              value={transcriptText}
              onChange={(e) => setTranscriptText(e.target.value)}
              rows={6}
              placeholder="0:00&#10;Dersin ilk cümlesi...&#10;0:15&#10;Devamı..."
              className="mt-2 w-full resize-y rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm outline-none focus:border-orange-400 dark:border-zinc-700 dark:bg-zinc-950"
            />
          </details>
          <div>
            <p className="mb-2 text-xs font-medium uppercase tracking-[0.18em] text-zinc-500">
              Ders
            </p>
            <div className="flex flex-wrap gap-2">
              {subjects.map((name) => {
                const on = subject === name;
                return (
                  <button
                    key={name}
                    type="button"
                    onClick={() => {
                      setSubject(name);
                      setSubjectType(isNumericalSubject(name) ? "sayisal" : "sozel");
                      if (!isNumericalSubject(name)) setFenBranch("");
                    }}
                    className={cn(
                      "rounded-full border px-3 py-1.5 text-sm transition",
                      on
                        ? "border-orange-400 bg-orange-500 text-zinc-950 shadow-[0_0_16px_rgba(251,146,60,0.4)]"
                        : "border-zinc-300 bg-white/40 text-zinc-600 hover:border-orange-400/60 dark:border-zinc-700 dark:bg-zinc-900/50 dark:text-zinc-300",
                    )}
                  >
                    {name}
                  </button>
                );
              })}
            </div>
          </div>
          <div className="grid gap-3 md:grid-cols-[140px_auto]">
            <Input
              type="number"
              min={5}
              max={20}
              value={count}
              onChange={(e) => setCount(Number(e.target.value))}
            />
            {outOfTrialCredits || outOfAdCredits ? (
              <ProUpgradeButton className="h-12" />
            ) : busy ? (
              <div className="flex min-w-0 gap-2">
                <Button
                  type="button"
                  size="lg"
                  disabled
                  className="h-12 min-w-0 flex-1"
                >
                  <Loader2 className="h-4 w-4 animate-spin" />
                  {elapsed
                    ? `Arka planda… ${elapsed}s`
                    : "Analiz ediliyor"}
                </Button>
                <Button
                  type="button"
                  size="lg"
                  variant="outline"
                  className="h-12 shrink-0 border-red-300 text-red-700 hover:border-red-500 hover:text-red-800 dark:border-red-800 dark:text-red-300"
                  onClick={() => cancelAnalyze()}
                >
                  Durdur
                </Button>
              </div>
            ) : adTier ? (
              <Button type="submit" size="lg" className="h-12">
                İzle & Çevir (Reklamlı) 📺
              </Button>
            ) : (
              <Button type="submit" size="lg" className="h-12">
                <Sparkles className="h-4 w-4" />
                Analiz et
              </Button>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            {(["sozel", "sayisal"] as const).map((kind) => (
              <button
                key={kind}
                type="button"
                onClick={() => {
                  setSubjectType(kind);
                  if (kind === "sozel") setFenBranch("");
                }}
                className={cn(
                  "rounded-full border px-3 py-1 text-[11px] font-medium uppercase tracking-[0.14em] transition",
                  subjectType === kind
                    ? "border-orange-400 bg-orange-500/15 text-orange-700 dark:text-orange-200"
                    : "border-zinc-200 text-zinc-500 dark:border-zinc-700",
                )}
              >
                {kind === "sayisal" ? "Sayısal" : "Sözel"}
              </button>
            ))}
          </div>
          {isYks ? (
            <FenLab
              branch={fenBranch}
              topic={subject}
              onBranch={(id, label) => {
                setFenBranch(id);
                setSubjectType("sayisal");
                setSubject(label);
              }}
              onTopic={(label) => {
                setSubjectType("sayisal");
                setSubject(label);
              }}
            />
          ) : null}
          {error ? <p className="text-sm text-red-400">{error}</p> : null}
          {busy ? (
            <p className="text-sm text-orange-700 dark:text-orange-200">
              {result
                ? `İlk dilimler hazır (${result.chunks_done ?? 1}/${result.chunks_total ?? 1}). Kalan 5 dakikalar kendiliğinden ekleniyor.`
                : `Hazırlanıyor… ${elapsed}s`}
            </p>
          ) : null}
          {result && !busy ? (
            <p className="text-sm text-emerald-700 dark:text-emerald-300">
              {result.notes.length} not ve {result.questions.length} soru hazır
              {result.cached ? " (kayıttan)" : ""}.{" "}
              <Link href="/notlarim" className="text-orange-700 dark:text-orange-300">
                Notlarımda duruyor →
              </Link>
            </p>
          ) : null}
          {adTier ? (
            <p className="text-sm text-zinc-500">
              Hey {profile.title}, deneme bitti. Ücretsiz modda günde 1 video, en fazla
              10 dakika. Sınırsız için{" "}
              <Link href="/pro" className="text-orange-600 dark:text-orange-300">
                Tilko Pro
              </Link>
              .
            </p>
          ) : null}
          {outOfTrialCredits ? (
            <p className="text-sm text-zinc-500">
              Hey {profile.title}, 7 ücretsiz hakkın bitti. Sınırsız analiz için{" "}
              <Link href="/pro" className="text-orange-600 dark:text-orange-300">
                Tilko Pro
              </Link>
              ’ya geç.
            </p>
          ) : null}
          {outOfAdCredits ? (
            <p className="text-sm text-zinc-500">
              Hey {profile.title}, günlük hakkın bitti! Yarın gece yarısı 1 hak
              yenilenir — ya da{" "}
              <Link href="/pro" className="text-orange-600 dark:text-orange-300">
                Tilko Pro
              </Link>
              .
            </p>
          ) : null}
        </form>
      </Card>

      <NotesPanel />
      <AdWatchModal
        open={adOpen}
        onClose={() => setAdOpen(false)}
        onComplete={() => void afterAd()}
      />

      <VideoRecs videos={profile.recommendedVideos} />
    </div>
  );
}
