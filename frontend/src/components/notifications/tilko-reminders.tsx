"use client";

import { useEffect, useRef } from "react";
import { Capacitor } from "@capacitor/core";
import { hardNavigate } from "@/lib/path";
import { isSignedIn } from "@/lib/auth";
import { useProfile } from "@/components/profile/profile-context";
import {
  readFavoriteTeacherVoice,
  refreshTeacherVoiceFromApi,
  styleCopyWithTeacher,
  type TeacherVoice,
} from "@/lib/teacher-voice";

const PREF_KEY = "tilko_notif_prefs_v2";
const CHANNEL_ID = "tilko_reminders";

export type NotifPrefs = {
  enabled: boolean;
  sazan: boolean;
  inactive: boolean;
  pro: boolean;
  traps: boolean;
};

const DEFAULT_PREFS: NotifPrefs = {
  enabled: true,
  sazan: true,
  inactive: true,
  pro: true,
  traps: true,
};

export function readNotifPrefs(): NotifPrefs {
  try {
    const raw =
      localStorage.getItem(PREF_KEY) || localStorage.getItem("tilko_notif_prefs_v1");
    if (!raw) return { ...DEFAULT_PREFS };
    return { ...DEFAULT_PREFS, ...JSON.parse(raw) };
  } catch {
    return { ...DEFAULT_PREFS };
  }
}

export function writeNotifPrefs(prefs: Partial<NotifPrefs>) {
  const next = { ...readNotifPrefs(), ...prefs };
  localStorage.setItem(PREF_KEY, JSON.stringify(next));
  window.dispatchEvent(new Event("tilko-notif-prefs"));
  return next;
}

type Copy = { title: string; body: string };

/** Gün + id + isim → aynı gün stabil, ertesi gün farklı. */
function pickCopy(pool: Copy[], seed: string): Copy {
  let h = 0;
  for (let i = 0; i < seed.length; i++) h = (h * 31 + seed.charCodeAt(i)) >>> 0;
  return pool[h % pool.length] || pool[0];
}

function dayKey(d = new Date()) {
  return `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`;
}

function fillWho(text: string, who: string) {
  const name = who.trim() || "Tilki";
  return text.replaceAll("{who}", name);
}

function atHour(daysFromNow: number, hour: number, minute = 0): Date {
  const d = new Date();
  d.setDate(d.getDate() + daysFromNow);
  d.setHours(hour, minute, 0, 0);
  if (daysFromNow === 0 && d.getTime() <= Date.now() + 60_000) {
    d.setDate(d.getDate() + 1);
  }
  return d;
}

function monthEndAt(hour = 19, minute = 0): Date {
  const now = new Date();
  const end = new Date(now.getFullYear(), now.getMonth() + 1, 0, hour, minute, 0, 0);
  if (end.getTime() <= Date.now() + 60_000) {
    return new Date(now.getFullYear(), now.getMonth() + 2, 0, hour, minute, 0, 0);
  }
  return end;
}

function fromNow(ms: number): Date {
  return new Date(Date.now() + ms);
}

const SAZAN_COPY: Copy[] = [
  {
    title: "Sazan zili çaldı",
    body: "{who}, bugünün tuzağı fırında. Kokusu geldi — ava!",
  },
  {
    title: "ÖSYM yine tuzak kurdu",
    body: "Sabah sabah çeldirici sıcak. {who}, bir ısırık al da görelim.",
  },
  {
    title: "Günün sazan menüsü hazır",
    body: "{who} için özel: tek soru, beş şık, bir gurur. Kaçırma!",
  },
  {
    title: "Tilki alarmı",
    body: "Sazan Avı kapıda. {who}, kuyruğunu sallama — içeri gir.",
  },
  {
    title: "Çeldirici taze geldi",
    body: "{who}, bu sabahki tuzak seni bekliyor. 60 saniye, sonra şık!",
  },
  {
    title: "Av alanı açıldı",
    body: "Bugün kimin sazan olacağı belli değil. {who}, iddiaya var mısın?",
  },
  {
    title: "KPSS / YKS sabah çayı",
    body: "Çay demlenirken bir Sazan Avı. {who}, fincanı bırakıp tuzağa bak.",
  },
];

const INACTIVE_COPY: Copy[] = [
  {
    title: "Sürü seni arıyor",
    body: "{who}, 3 gündür radarda yoksun. Tilkiler merak etti — bir bakıver.",
  },
  {
    title: "Tozlandın biraz",
    body: "Defter seni özledi. {who}, 5 dakikalık dönüş turu atalım mı?",
  },
  {
    title: "Kaçak tilki ihbarı",
    body: "{who} kayıp ilanı: son görülme 3 gün önce. Av’a dön!",
  },
  {
    title: "Sazanlar fırsat bilmiş",
    body: "Sen yokken çeldiriciler şımardı. {who}, hadi disipline!",
  },
  {
    title: "Miss like you",
    body: "Şaka bir yana: {who}, kısa bir analiz veya Sazan Avı seni bekliyor.",
  },
  {
    title: "Uyuyan tilki uyan",
    body: "3 günlük tatil bitti. {who}, bir yanlışa rövanş alma vakti.",
  },
];

const PRO_UPSELL_COPY: Copy[] = [
  {
    title: "Kota tilkisi kapıda",
    body: "{who}, ücretsiz kota yetmeyebilir. Pro’da sınırsız not — Play’e göz at.",
  },
  {
    title: "Sazan geçidi ücretli mi?",
    body: "Şaka: Pro’da geçit bedava gibi. {who}, sınırsız analiz için bakıver.",
  },
  {
    title: "Kota bitmeden haber",
    body: "{who}, Tilko Pro = bekleme yok, limit yok. Merak ettiysen Play’de.",
  },
  {
    title: "Premium tilki kulübü",
    body: "İçeride çeldirici avı sınırsız. {who}, kapı Play Store’da.",
  },
];

const TRAP_24H: Copy[] = [
  {
    title: "Dünün intikamı",
    body: "{who}, dünkü çeldirici hâlâ sırıtıyor. 5 dk defter — rövanş!",
  },
  {
    title: "Tilki geri döndü",
    body: "Yanlışın üstüne bir gece geçmiş. {who}, tuzak defterinde hesap sor!",
  },
  {
    title: "Çeldiriciye mektup",
    body: "“Seni unutmadım.” — {who}. Defteri aç, 3 tuzak çöz.",
  },
  {
    title: "24 saat kuralı",
    body: "Taze yanlışlar en lezzetli rövanş. {who}, tuzak defterine!",
  },
  {
    title: "Sazan geri zıpladı",
    body: "{who}, o şık hâlâ aklında mı? Defterde yüzleşelim.",
  },
];

const TRAP_3D: Copy[] = [
  {
    title: "Sazanlar toplanıyor",
    body: "3 gündür deftere bakmadın. {who}, yanlışların parti veriyor — bas!",
  },
  {
    title: "Üç günlük toz",
    body: "{who}, tuzaklar tozlanmış. Silkele, 5 soruluk av başlasın.",
  },
  {
    title: "Çeldirici sendromu",
    body: "Belirtiler: unutmak. Tedavi: tuzak defteri. Doktor: {who}.",
  },
  {
    title: "Mahalle baskısı",
    body: "Diğer tilkiler defteri bitirdi. {who}, sen nerdesin?",
  },
  {
    title: "3 gün sonra",
    body: "ÖSYM unutmaz, sen de unutma. {who}, yanlışlarına dön!",
  },
];

const TRAP_7D: Copy[] = [
  {
    title: "Haftalık hesaplaşma",
    body: "{who}, bir haftalık tuzaklar birikti. 10’luk rövanş seti hazır!",
  },
  {
    title: "Pazar pazarı değil",
    body: "Haftanın yanlışları indirimde değil — {who} avında. Deftere!",
  },
  {
    title: "7 gün sonra aynı tuzak",
    body: "Tekrar düşme. {who}, tuzak defterinde aşı ol.",
  },
  {
    title: "Haftalık tilki raporu",
    body: "Skor: yarım. Potansiyel: full. {who}, defteri açıp düzelt.",
  },
  {
    title: "Rövanş gecesi",
    body: "Bu haftanın çeldiricileri seni çağırıyor. {who}, sahneye!",
  },
];

const TRAP_MONTH: Copy[] = [
  {
    title: "Ay sonu tilki mahkemesi",
    body: "{who}, bu ayın yanlışları jüride. Defter + mini quiz — beraat et!",
  },
  {
    title: "Aylık sazan bilançosu",
    body: "Kâr-zarar: çeldiriciler. {who}, kapanış toplantısı tuzak defterinde.",
  },
  {
    title: "Ayı kapatırken",
    body: "Yeni ay temiz gelsin. {who}, eski tuzakları yakıp kül et!",
  },
  {
    title: "Mahkeme saat 19:00",
    body: "Sanık: yanlış şıklar. Avukat: {who}. Delil: tuzak defteri.",
  },
  {
    title: "Ay sonu boss fight",
    body: "Final boss: kendi yanlışların. {who}, defteri aç ve kazan.",
  },
];

type Scheduled = {
  id: number;
  title: string;
  body: string;
  schedule: { at: Date; allowWhileIdle: boolean };
  channelId: string;
  extra: { route: string };
};

function line(
  id: number,
  pool: Copy[],
  who: string,
  at: Date,
  route: string,
  voice: TeacherVoice | null,
  salt = "",
): Scheduled {
  const seed = `${dayKey(at)}|${id}|${who}|${salt}|${voice?.name || ""}`;
  const raw = pickCopy(pool, seed);
  const filled = {
    title: fillWho(raw.title, who),
    body: fillWho(raw.body, who),
  };
  const styled = styleCopyWithTeacher(filled, voice, seed);
  return {
    id,
    title: styled.title,
    body: styled.body,
    schedule: { at, allowWhileIdle: true },
    channelId: CHANNEL_ID,
    extra: { route },
  };
}

async function loadPlugin() {
  if (!Capacitor.isNativePlatform()) return null;
  try {
    const mod = await import("@capacitor/local-notifications");
    return mod.LocalNotifications;
  } catch {
    return null;
  }
}

export async function syncTilkoReminders(opts: {
  isPremium: boolean;
  prefs?: NotifPrefs;
  title?: string;
  voice?: TeacherVoice | null;
}) {
  const LocalNotifications = await loadPlugin();
  if (!LocalNotifications) return { ok: false, reason: "web" as const };

  const prefs = opts.prefs || readNotifPrefs();
  const who = (opts.title || "").trim() || "Tilki";
  const voice =
    opts.voice !== undefined ? opts.voice : readFavoriteTeacherVoice();
  const pending = await LocalNotifications.getPending();
  const cancelIds = (pending.notifications || [])
    .map((n) => n.id)
    .filter((id) => id >= 1100 && id < 1200);
  if (cancelIds.length) {
    await LocalNotifications.cancel({
      notifications: cancelIds.map((id) => ({ id })),
    });
  }

  if (!prefs.enabled) {
    return { ok: true, reason: "disabled" as const };
  }

  const perm = await LocalNotifications.requestPermissions();
  if (perm.display !== "granted") {
    return { ok: false, reason: "denied" as const };
  }

  try {
    await LocalNotifications.createChannel({
      id: CHANNEL_ID,
      name: "Tilko hatırlatmalar",
      description: "Sazan Avı, tuzak defteri ve Pro hatırlatmaları",
      importance: 4,
      visibility: 1,
      vibration: true,
    });
  } catch {
    /* ignore */
  }

  const notifications: Scheduled[] = [];

  if (prefs.sazan) {
    for (let i = 0; i < 7; i++) {
      const at = atHour(i, 9, 0);
      notifications.push(
        line(1101 + i, SAZAN_COPY, who, at, "/gunluk-gorevler", voice, `sazan-${i}`),
      );
    }
  }

  if (prefs.inactive) {
    notifications.push(
      line(1110, INACTIVE_COPY, who, fromNow(3 * 24 * 60 * 60 * 1000), "/", voice),
    );
  }

  if (prefs.pro && !opts.isPremium) {
    notifications.push(
      line(1111, PRO_UPSELL_COPY, who, fromNow(2 * 24 * 60 * 60 * 1000), "/pro", voice),
    );
  }

  if (prefs.traps && opts.isPremium) {
    notifications.push(
      line(1120, TRAP_24H, who, fromNow(24 * 60 * 60 * 1000), "/tuzak-defteri", voice),
    );
    notifications.push(
      line(1121, TRAP_3D, who, fromNow(3 * 24 * 60 * 60 * 1000), "/tuzak-defteri", voice),
    );
    notifications.push(
      line(1122, TRAP_7D, who, fromNow(7 * 24 * 60 * 60 * 1000), "/tuzak-defteri", voice),
    );
    notifications.push(
      line(
        1123,
        TRAP_MONTH,
        who,
        monthEndAt(19, 0),
        "/tuzak-defteri",
        voice,
        "month-end",
      ),
    );
  }

  if (notifications.length) {
    await LocalNotifications.schedule({ notifications });
  }
  return { ok: true, reason: "scheduled" as const, count: notifications.length };
}

export function TilkoRemindersBoot() {
  const { profile, ready } = useProfile();
  const listening = useRef(false);

  useEffect(() => {
    if (!ready || !isSignedIn()) return;
    if (!Capacitor.isNativePlatform()) return;

    const run = async () => {
      const voice = await refreshTeacherVoiceFromApi();
      await syncTilkoReminders({
        isPremium: profile.isPremium,
        title: profile.title,
        voice,
      });
    };
    void run();

    if (listening.current) return;
    listening.current = true;

    let handle: { remove: () => Promise<void> } | null = null;
    void (async () => {
      const LocalNotifications = await loadPlugin();
      if (!LocalNotifications) return;
      handle = await LocalNotifications.addListener(
        "localNotificationActionPerformed",
        (event) => {
          const route = String(
            (event.notification.extra as { route?: string } | undefined)?.route || "",
          ).trim();
          if (route.startsWith("/")) {
            hardNavigate(route);
          }
        },
      );
    })();

    const onPrefs = () => {
      void syncTilkoReminders({
        isPremium: profile.isPremium,
        title: profile.title,
      });
    };
    const onVoice = () => {
      void syncTilkoReminders({
        isPremium: profile.isPremium,
        title: profile.title,
      });
    };
    window.addEventListener("tilko-notif-prefs", onPrefs);
    window.addEventListener("tilko-teacher-voice", onVoice);
    return () => {
      window.removeEventListener("tilko-notif-prefs", onPrefs);
      window.removeEventListener("tilko-teacher-voice", onVoice);
      void handle?.remove();
      listening.current = false;
    };
  }, [ready, profile.isPremium, profile.title]);

  return null;
}
