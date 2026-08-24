import type { NoteItem, TrapItem } from "@/lib/api";
import type { HumanNoteCardProps } from "@/components/notes/human-note-card";

function asArrow(line: string) {
  const trimmed = line.trim();
  if (!trimmed) return "";
  if (/^(->|=>|≠|\*)/.test(trimmed)) return trimmed;
  return `-> ${trimmed}`;
}

function clip(text: string, max = 90) {
  const clean = text.replace(/\s+/g, " ").trim();
  if (clean.length <= max) return clean;
  return `${clean.slice(0, max).trim()}…`;
}

/** Model/sistem hatası exam_tip olarak kırmızı kutuya basılmasın. */
function isSystemExamTip(tip: string) {
  return /çalışılabilir\s*not|model\s*bu\s*dilimde|başka\s*bölüm\s*veya|yeterli\s*altyazı|hourly\s*limit|rate[\s-]*limit|i\s*cannot|try\s*again\s*later|cannot\s*provide|knowledge\s*base|analiz\s*şu\s*an/i.test(
    tip,
  );
}

export function fromNoteItem(note: NoteItem, tilt = -0.6): HumanNoteCardProps {
  const raw =
    note.key_points.length > 0
      ? note.key_points
      : note.text.split(/[.!?]\s+/).filter((part) => part.trim().length > 8);
  const lines = raw.slice(0, 8).map((line) => asArrow(clip(line, 110)));
  const highlights = [note.title].filter(Boolean);
  const tip = (note.exam_tip || "").trim();

  return {
    title: note.title || "Ders notu",
    stamp: note.timestamp_label,
    tilt,
    highlights,
    lines,
    mnemonic: note.mnemonic ? clip(note.mnemonic, 140) : undefined,
    warning: tip && !isSystemExamTip(tip) ? tip : undefined,
  };
}

export function fromTrapItem(trap: TrapItem, tilt = 0.8): HumanNoteCardProps {
  const options = Object.entries(trap.options || {}).map(
    ([letter, text]) => `${letter}) ${clip(text, 70)}`,
  );
  return {
    variant: "trap",
    title: trap.topic || "Tuzak analizi",
    stamp: `tekrar #${trap.review_count}`,
    tilt,
    highlights: [trap.chosen, trap.correct].filter(Boolean),
    lines: [
      asArrow(clip(trap.question_text, 140)),
      ...options,
      `ben -> ${trap.chosen || "?"}    doğru => ${trap.correct || "?"}`,
    ],
    subject: trap.misconception_tag || (trap.subject_type === "sayisal" ? "Sayısal" : undefined),
    mnemonic: trap.shortcut_tactic
      ? clip(trap.shortcut_tactic, 160)
      : trap.explanation
        ? clip(trap.explanation, 160)
        : undefined,
    teacherNote: trap.teacher_note || trap.distractor_analysis || undefined,
    warning:
      trap.time_trap_triggered
        ? "Bilgiden değil, süreden kaybettin. 60 sn kuralı."
        : undefined,
  };
}
