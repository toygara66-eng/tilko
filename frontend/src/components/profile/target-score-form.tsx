"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { useProfile } from "@/components/profile/profile-context";
import { setTargetScore } from "@/lib/api";
import { getUserId } from "@/lib/user";

export function TargetScoreForm() {
  const { profile, apply, refresh } = useProfile();
  const [value, setValue] = useState(String(Math.round(profile.targetScore || 85)));
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");

  useEffect(() => {
    setValue(String(Math.round(profile.targetScore || 85)));
  }, [profile.targetScore]);

  async function save() {
    const parsed = Number(value);
    if (!Number.isFinite(parsed) || parsed < 1 || parsed > 100) {
      setNote("1 ile 100 arasında bir puan yaz.");
      return;
    }
    setBusy(true);
    setNote("");
    try {
      const data = await setTargetScore(getUserId(), parsed);
      apply({
        targetScore: data.target_score,
        targetIsSet: true,
        progressPct: Math.min(
          100,
          Math.round((100 * Math.max(profile.currentScore, 0)) / data.target_score),
        ),
      });
      setNote(data.message);
      void refresh();
    } catch (err) {
      setNote(err instanceof Error ? err.message : "Hedef kaydedilemedi");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="rounded-2xl border border-orange-400/40 bg-white/55 p-5 backdrop-blur-xl dark:bg-zinc-950/45">
      <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-orange-600 dark:text-orange-300">
        Hedef puan
      </p>
      <p className="mt-1 text-xs text-zinc-500">
        Teşhis ölçeği 0–100. Ana sayfadaki çubuk bu hedefe göre dolar.
      </p>
      <div className="mt-3 flex items-center gap-2">
        <input
          type="number"
          min={1}
          max={100}
          inputMode="numeric"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          className="h-10 w-20 rounded-xl border border-orange-400/40 bg-white/70 px-3 text-sm tabular-nums text-zinc-900 outline-none focus:border-orange-400 dark:bg-zinc-900/70 dark:text-zinc-100"
        />
        <Button size="sm" disabled={busy} onClick={() => void save()}>
          Kaydet
        </Button>
      </div>
      {note ? <p className="mt-2 text-xs text-zinc-500">{note}</p> : null}
    </section>
  );
}
