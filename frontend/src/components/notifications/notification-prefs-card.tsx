"use client";

import { useEffect, useState } from "react";
import { Bell } from "lucide-react";
import {
  readNotifPrefs,
  syncTilkoReminders,
  writeNotifPrefs,
  type NotifPrefs,
} from "@/components/notifications/tilko-reminders";
import { useProfile } from "@/components/profile/profile-context";
import { Capacitor } from "@capacitor/core";

function Toggle({
  label,
  hint,
  checked,
  onChange,
}: {
  label: string;
  hint: string;
  checked: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <label className="flex cursor-pointer items-start justify-between gap-3 rounded-xl border border-zinc-200/80 px-3 py-2.5 dark:border-zinc-800">
      <span className="min-w-0">
        <span className="block text-sm font-medium text-zinc-800 dark:text-zinc-100">
          {label}
        </span>
        <span className="mt-0.5 block text-xs text-zinc-500">{hint}</span>
      </span>
      <input
        type="checkbox"
        className="mt-1 h-4 w-4 accent-orange-500"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
      />
    </label>
  );
}

const DEFAULT_SAFE: NotifPrefs = {
  enabled: true,
  sazan: true,
  inactive: true,
  pro: true,
  traps: true,
};

export function NotificationPrefsCard() {
  const { profile } = useProfile();
  const [prefs, setPrefs] = useState<NotifPrefs>(DEFAULT_SAFE);
  const [msg, setMsg] = useState("");
  const native = typeof window !== "undefined" && Capacitor.isNativePlatform();

  useEffect(() => {
    setPrefs(readNotifPrefs());
  }, []);

  async function update(patch: Partial<NotifPrefs>) {
    const next = writeNotifPrefs(patch);
    setPrefs(next);
    setMsg("");
    if (!native) {
      setMsg("Bildirimler Android uygulamasında çalışır.");
      return;
    }
    const result = await syncTilkoReminders({
      isPremium: profile.isPremium,
      prefs: next,
      title: profile.title,
    });
    if (result.reason === "denied") {
      setMsg("Bildirim izni kapalı. Telefon ayarlarından Tilko’ya izin ver.");
    } else if (result.ok) {
      setMsg("Hatırlatmalar güncellendi.");
    }
  }

  return (
    <section className="rounded-2xl border border-orange-400/40 bg-white/55 p-5 backdrop-blur-xl dark:bg-zinc-950/45">
      <div className="flex items-center gap-2">
        <Bell className="h-4 w-4 text-orange-600 dark:text-orange-300" />
        <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-orange-600 dark:text-orange-300">
          Bildirimler
        </p>
      </div>
      <p className="mt-2 text-xs text-zinc-500">
        Metinler her gün değişir, rütbene göre hitap eder — Sazan, dönüş, Pro ve
        tuzak defteri rövanşları.
      </p>
      <div className="mt-3 space-y-2">
        <Toggle
          label="Bildirimleri aç"
          hint="Tüm hatırlatmaların ana anahtarı"
          checked={prefs.enabled}
          onChange={(enabled) => void update({ enabled })}
        />
        <Toggle
          label="Sazan Avı"
          hint="Her sabah 09:00 — yeni tuzak düştü"
          checked={prefs.sazan}
          onChange={(sazan) => void update({ sazan })}
        />
        <Toggle
          label="Geri dön"
          hint="3 gündür girmezsen hatırlatır"
          checked={prefs.inactive}
          onChange={(inactive) => void update({ inactive })}
        />
        {!profile.isPremium ? (
          <Toggle
            label="Pro hatırlatması"
            hint="Ücretsizken kota için nazik yönlendirme"
            checked={prefs.pro}
            onChange={(pro) => void update({ pro })}
          />
        ) : (
          <Toggle
            label="Tuzak defteri rövanşı"
            hint="24 saat · 3 gün · 7 gün · ay sonu — yanlışlara eğlenceli dönüş"
            checked={prefs.traps}
            onChange={(traps) => void update({ traps })}
          />
        )}
      </div>
      {msg ? <p className="mt-3 text-xs text-zinc-500">{msg}</p> : null}
    </section>
  );
}
