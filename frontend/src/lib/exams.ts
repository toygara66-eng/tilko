export const EXAM_OPTIONS = [
  {
    id: "kpss",
    title: "KPSS",
    hint: "Lisans / Önlisans / Ortaöğretim",
    emoji: "🦊",
    children: [
      { id: "kpss_lisans", label: "Lisans" },
      { id: "kpss_onlisans", label: "Önlisans" },
      { id: "kpss_ortaogretim", label: "Ortaöğretim" },
    ],
  },
  {
    id: "yks",
    title: "YKS",
    hint: "Üniversite — TYT/AYT",
    emoji: "🎓",
    children: [{ id: "yks", label: "TYT / AYT" }],
  },
  {
    id: "oabt",
    title: "ÖABT",
    hint: "Alan dersleri / öğretmenlik",
    emoji: "📘",
    children: [{ id: "oabt", label: "Alan bilgisi" }],
  },
  {
    id: "diger",
    title: "Diğer Sınavlar",
    hint: "LGS ve genel ÖSYM tarzı",
    emoji: "🎯",
    children: [
      { id: "lgs", label: "LGS" },
      { id: "other", label: "Diğer" },
    ],
  },
] as const;

export type ExamTargetId =
  | "kpss_lisans"
  | "kpss_onlisans"
  | "kpss_ortaogretim"
  | "yks"
  | "oabt"
  | "lgs"
  | "other";

export function familyOf(target: string): string {
  if (target.startsWith("kpss")) return "kpss";
  if (target === "lgs" || target === "other") return "diger";
  return target;
}

export const SUBJECTS_BY_FAMILY: Record<string, string[]> = {
  kpss: ["Türkçe", "Matematik", "Tarih", "Coğrafya", "Vatandaşlık", "Güncel"],
  yks: ["Türkçe", "Matematik", "Fizik", "Kimya", "Biyoloji", "Tarih", "Coğrafya"],
  oabt: ["Alan bilgisi", "Ölçme-değerlendirme", "Öğrenme kuramı"],
  lgs: ["Türkçe", "Matematik", "Fen", "İnkılap"],
  other: ["Türkçe", "Matematik", "Genel kültür"],
};

export function subjectsFor(target: string): string[] {
  if (target.startsWith("kpss")) return SUBJECTS_BY_FAMILY.kpss;
  return SUBJECTS_BY_FAMILY[target] || SUBJECTS_BY_FAMILY.kpss;
}

export function isNumericalSubject(name: string): boolean {
  return /matematik|fizik|kimya|biyoloji|\bfen\b/i.test(name);
}
