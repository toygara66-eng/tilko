/** Favori hoca üslubu — yerel skor + API senkronu (bildirim kişiselleştirme). */

import { getTeacherVoice } from "@/lib/api";
import { getUserId } from "@/lib/user";

const STORE_KEY = "tilko_teacher_voice_v1";

export type TeacherVoice = {
  name: string;
  catchphrases: string[];
  tone: string;
  score?: number;
};

type Store = {
  teachers: Record<
    string,
    { name: string; score: number; catchphrases: string[]; tone: string }
  >;
  updatedAt: number;
};

function fold(s: string) {
  return s.trim().toLocaleLowerCase("tr").replace(/\s+/g, " ");
}

function emptyStore(): Store {
  return { teachers: {}, updatedAt: 0 };
}

function readStore(): Store {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    if (!raw) return emptyStore();
    const parsed = JSON.parse(raw) as Store;
    return {
      teachers: parsed.teachers || {},
      updatedAt: Number(parsed.updatedAt) || 0,
    };
  } catch {
    return emptyStore();
  }
}

function writeStore(store: Store) {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(store));
    window.dispatchEvent(new Event("tilko-teacher-voice"));
  } catch {
    /* ignore */
  }
}

function mergePhrases(a: string[], b: string[], limit = 10): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  for (const p of [...a, ...b]) {
    const t = (p || "").trim();
    if (!t) continue;
    const k = t.toLocaleLowerCase("tr");
    if (seen.has(k)) continue;
    seen.add(k);
    out.push(t);
    if (out.length >= limit) break;
  }
  return out;
}

/** Analiz bitince çağır — hoca skorunu artırır. */
export function learnTeacherVoice(input: {
  name?: string | null;
  catchphrases?: string[] | null;
  tone?: string | null;
  weight?: number;
}) {
  const name = (input.name || "").trim();
  const phrases = (input.catchphrases || []).map((p) => p.trim()).filter(Boolean);
  const tone = (input.tone || "").trim() || "öğretici, net";
  if (!name && !phrases.length) return;

  const store = readStore();
  const key = name ? fold(name) : "__anon__";
  const prev = store.teachers[key] || {
    name: name || "",
    score: 0,
    catchphrases: [],
    tone,
  };
  store.teachers[key] = {
    name: name || prev.name,
    score: prev.score + Math.max(1, input.weight || 1),
    catchphrases: mergePhrases(prev.catchphrases, phrases),
    tone: tone || prev.tone,
  };
  store.updatedAt = Date.now();
  writeStore(store);
}

export function readFavoriteTeacherVoice(): TeacherVoice | null {
  const store = readStore();
  const rows = Object.values(store.teachers).filter((t) => t.score > 0 || t.name);
  if (!rows.length) return null;
  rows.sort((a, b) => b.score - a.score);
  const top = rows[0];
  if (!top) return null;
  return {
    name: top.name,
    catchphrases: top.catchphrases,
    tone: top.tone,
    score: top.score,
  };
}

/** Sunucudaki notlardan favori hocayı çekip yerelle birleştir. */
export async function refreshTeacherVoiceFromApi(): Promise<TeacherVoice | null> {
  const uid = getUserId();
  if (!uid || uid === "local" || uid.startsWith("aday-")) {
    return readFavoriteTeacherVoice();
  }
  try {
    const remote = await getTeacherVoice(uid);
    const name = (remote.name || "").trim();
    if (name || (remote.catchphrases || []).length) {
      learnTeacherVoice({
        name,
        catchphrases: remote.catchphrases,
        tone: remote.tone,
        weight: Math.max(1, Math.min(20, Number(remote.notes) || 3)),
      });
    }
  } catch {
    /* çevrimdışı / 403 */
  }
  return readFavoriteTeacherVoice();
}

/** Bildirim metnini hoca hitabı + tonla süsle. */
export function styleCopyWithTeacher(
  copy: { title: string; body: string },
  voice: TeacherVoice | null,
  seed: string,
): { title: string; body: string } {
  if (!voice || (!voice.name && !voice.catchphrases.length)) {
    return copy;
  }

  let h = 0;
  for (let i = 0; i < seed.length; i++) h = (h * 31 + seed.charCodeAt(i)) >>> 0;

  const hoca = (voice.name || "").trim();
  const short =
    hoca.split(/\s+/).length > 2
      ? hoca.split(/\s+/).slice(0, 2).join(" ")
      : hoca;
  const phrase =
    voice.catchphrases.length > 0
      ? voice.catchphrases[h % voice.catchphrases.length]
      : "";

  const titlePool = hoca
    ? [
        `${short} Hoca'dan`,
        `${short} arıyor`,
        `${short} Hoca zili`,
        copy.title,
      ]
    : [copy.title];
  const title = titlePool[h % titlePool.length] || copy.title;

  let body = copy.body;
  if (phrase) {
    const openers = [
      `${phrase} — ${body}`,
      `${phrase}! ${body}`,
      `Bak ${phrase.toLocaleLowerCase("tr")}: ${body}`,
    ];
    body = openers[h % openers.length] || body;
  }

  const tone = (voice.tone || "").toLocaleLowerCase("tr");
  if (tone.includes("otoriter") || tone.includes("sert")) {
    body = body
      .replace(/mı\?/gi, " — şimdi.")
      .replace(/misin\?/gi, ".")
      .replace(/lütfen/gi, "");
  } else if (tone.includes("samimi")) {
    if (!/[!…]$/.test(body.trim())) {
      body = `${body.trim()} Hadi!`;
    }
  }

  if (body.length > 220) {
    body = `${body.slice(0, 217).trim()}…`;
  }

  return { title: title.slice(0, 80), body };
}
