/** Sınav tarihleri — backend `exams.py` ile aynı. Geçmişse bir yıl ötele. */

export const EXAM_DATES: Record<string, string> = {
  kpss_lisans: "2026-09-06",
  kpss_onlisans: "2026-09-13",
  kpss_ortaogretim: "2026-09-13",
  yks: "2027-06-20",
  oabt: "2026-09-20",
  lgs: "2027-06-14",
  other: "2026-09-06",
};

export const EXAM_DATE = new Date(2026, 8, 6);

function parseStamp(raw: string) {
  const [year, month, day] = raw.split("-").map(Number);
  return new Date(year, (month || 1) - 1, day || 1);
}

export function examDateFor(examTarget?: string, now = new Date()) {
  const key = (examTarget || "kpss_lisans").trim() || "kpss_lisans";
  const stamp = parseStamp(EXAM_DATES[key] || EXAM_DATES.kpss_lisans);
  const start = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  while (stamp < start) {
    stamp.setFullYear(stamp.getFullYear() + 1);
  }
  return stamp;
}

export function daysUntilExam(now = new Date(), examTarget?: string) {
  const start = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const exam = examDateFor(examTarget, now);
  return Math.round((exam.getTime() - start.getTime()) / 86_400_000);
}
