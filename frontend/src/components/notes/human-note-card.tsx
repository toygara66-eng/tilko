"use client";

import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { useNoteMode } from "@/components/notes/note-mode";

export type HumanNoteCardProps = {
  title: string;
  subject?: string;
  lines: string[];
  highlights?: string[];
  warning?: string;
  teacherNote?: string;
  mnemonic?: string;
  stamp?: string;
  tilt?: number;
  variant?: "paper" | "sticky" | "trap";
  footer?: ReactNode;
};

export function HocaNote({ text }: { text: string }) {
  const { isHandwrittenMode } = useNoteMode();
  if (!text.trim()) return null;
  return (
    <div
      className={cn(
        "mt-4 w-full max-w-full px-3 py-2 leading-snug sm:mt-5 sm:max-w-[92%]",
        isHandwrittenMode
          ? "rounded-sm border border-red-700/25 bg-red-50/70 note-scribble text-[1.05rem] text-red-600 sm:-rotate-1 sm:text-[1.2rem] sm:ml-auto"
          : "rounded-xl border border-red-200 bg-red-50/80 note-scribble text-base text-red-700 dark:border-red-500/35 dark:bg-red-950/50 dark:text-red-300 sm:text-lg",
      )}
    >
      <p className="mb-1 text-[0.65rem] font-semibold uppercase tracking-[0.18em] text-red-500 sm:text-[0.7rem]">
        Hoca notu
      </p>
      <p className="break-words">{text}</p>
    </div>
  );
}

export function Highlighter({
  children,
  handwritten,
}: {
  children: ReactNode;
  handwritten: boolean;
}) {
  if (!handwritten) {
    return <strong className="font-bold text-blue-700 dark:text-blue-400">{children}</strong>;
  }
  return (
    <mark className="highlighter-mark rounded-sm bg-yellow-300/60 px-0.5 text-inherit shadow-[inset_0_-0.35em_0_rgb(250_204_21_/_0.45)] [-webkit-box-decoration-break:clone] [box-decoration-break:clone] sm:px-1">
      {children}
    </mark>
  );
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function ink(
  text: string,
  highlights: string[] = [],
  handwritten = true,
): ReactNode {
  const words = highlights.map((w) => w.trim()).filter((w) => w.length > 1);
  if (!words.length) return text;
  const pattern = new RegExp(`(${words.map(escapeRegExp).join("|")})`, "gi");
  const parts = text.split(pattern);
  return parts.map((part, index) => {
    const hit = words.some((w) => w.toLowerCase() === part.toLowerCase());
    return hit ? (
      <Highlighter key={`${part}-${index}`} handwritten={handwritten}>
        {part}
      </Highlighter>
    ) : (
      part
    );
  });
}

export function HumanNoteCard({
  title,
  subject,
  lines,
  highlights = [],
  warning,
  teacherNote,
  mnemonic,
  stamp,
  tilt = -0.8,
  variant = "paper",
  footer,
}: HumanNoteCardProps) {
  const { isHandwrittenMode } = useNoteMode();
  const caution = warning?.replace(/^\s*(⚠️\s*)?dikkat\s*:?\s*/i, "").trim();

  const paper =
    variant === "sticky"
      ? "bg-yellow-100/90"
      : variant === "trap"
        ? "bg-orange-50/90"
        : "note-paper bg-amber-50/90";

  return (
    <article
      style={{
        // Telefonlarda rotate komşu kartlarla üst üste biniyor.
        transform: isHandwrittenMode ? `rotate(${tilt * 0.35}deg)` : undefined,
      }}
      className={cn(
        "relative mt-3 overflow-hidden px-4 pt-6 transition-colors sm:overflow-visible sm:px-6 sm:pt-7",
        isHandwrittenMode
          ? cn(
              "note-hand rounded-sm border border-amber-900/15 pb-6 text-slate-900 shadow-[4px_8px_24px_rgba(0,0,0,0.28)] sm:pb-8",
              paper,
            )
          : "rounded-2xl border border-zinc-200 bg-white pb-6 font-sans text-zinc-900 shadow-none dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-100",
      )}
    >
      {isHandwrittenMode ? (
        <>
          <div
            aria-hidden
            className="absolute left-1/2 top-0 hidden h-7 w-28 -translate-x-1/2 -translate-y-1/2 rotate-1 bg-amber-200/80 shadow-sm sm:block"
          />
          <div
            aria-hidden
            className="pointer-events-none absolute inset-y-0 left-5 w-px bg-red-400/35 sm:left-10 sm:bg-red-400/40"
          />
        </>
      ) : null}

      <header
        className={cn(
          "mb-3 flex flex-col gap-1 sm:mb-4 sm:flex-row sm:items-baseline sm:justify-between sm:gap-3",
          isHandwrittenMode ? "pl-3 sm:pl-4" : "pl-0",
        )}
      >
        <div className="min-w-0 flex-1">
          {subject ? (
            <p
              className={cn(
                "leading-none",
                isHandwrittenMode
                  ? "note-scribble text-base text-sky-800/80 sm:text-lg"
                  : "font-sans text-xs font-medium uppercase tracking-widest text-zinc-500",
              )}
            >
              {subject}
            </p>
          ) : null}
          <h3
            className={cn(
              "break-words tracking-tight",
              isHandwrittenMode
                ? "note-hand text-[1.45rem] font-bold leading-snug text-slate-900 sm:text-3xl sm:leading-tight"
                : "font-sans text-lg font-semibold leading-snug text-zinc-900 dark:text-zinc-50 sm:text-xl",
            )}
          >
            {ink(title, highlights, isHandwrittenMode)}
          </h3>
        </div>
        {stamp ? (
          <span
            className={cn(
              "shrink-0",
              isHandwrittenMode
                ? "note-scribble text-sm text-slate-500 sm:text-base"
                : "font-sans text-xs text-zinc-500",
            )}
          >
            {stamp}
          </span>
        ) : null}
      </header>

      <ul
        className={cn(
          "space-y-2 sm:space-y-1.5",
          isHandwrittenMode
            ? "pl-3 note-hand text-[1.05rem] leading-relaxed text-slate-800 sm:pl-4 sm:text-[1.3rem] sm:leading-snug"
            : "pl-0 font-sans text-sm leading-relaxed text-zinc-700 dark:text-zinc-300",
        )}
      >
        {lines.map((line, index) => (
          <li key={`${line}-${index}`} className="break-words">
            {ink(line, highlights, isHandwrittenMode)}
          </li>
        ))}
      </ul>

      {mnemonic ? (
        <p
          className={cn(
            "mt-3 break-words sm:mt-4",
            isHandwrittenMode
              ? "pl-3 note-scribble text-xl leading-snug text-sky-900 sm:pl-4 sm:text-2xl"
              : "pl-0 font-sans text-sm font-medium text-blue-700 dark:text-blue-400",
          )}
        >
          * {ink(mnemonic, highlights, isHandwrittenMode)}
        </p>
      ) : null}

      {teacherNote ? (
        <div className={isHandwrittenMode ? "pl-3 sm:pl-4" : ""}>
          <HocaNote text={teacherNote} />
        </div>
      ) : null}

      {caution ? (
        isHandwrittenMode ? (
          <div
            role="alert"
            className="mt-4 break-words rounded-sm border border-red-600/25 bg-red-50/80 px-3 py-2 note-scribble text-[1.05rem] leading-snug text-red-700 sm:mt-5 sm:text-[1.25rem]"
          >
            <span className="font-semibold">⚠️ DİKKAT: </span>
            {ink(caution, highlights, true)}
          </div>
        ) : (
          <div
            role="alert"
            className="mt-5 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-500/30 dark:bg-red-950/40 dark:text-red-200"
          >
            <p className="mb-1 font-semibold text-red-700 dark:text-red-300">Dikkat</p>
            <p className="leading-relaxed text-red-800/90 dark:text-red-100/90">
              {ink(caution, highlights, false)}
            </p>
          </div>
        )
      ) : null}

      {footer ? (
        <div
          className={cn(
            "mt-4 min-w-0",
            isHandwrittenMode
              ? "pl-3 note-scribble text-base text-sky-800 sm:pl-4 sm:text-lg"
              : "pl-0 font-sans text-sm text-blue-700 dark:text-blue-400",
          )}
        >
          {footer}
        </div>
      ) : null}
    </article>
  );
}

export function sampleHistoryNote(rankTitle: string): HumanNoteCardProps {
  return {
    title: "Tanzimat ≠ Islahat",
    subject: "KPSS Tarih · 19. yy",
    stamp: "12:04",
    tilt: -1.2,
    highlights: [
      "Tanzimat",
      "Islahat",
      "1839",
      "1856",
      "Mustafa Reşid",
      "eşitlik",
      "Meşrutiyet",
    ],
    lines: [
      "Tanzimat (1839) -> Gülhane Hatt-ı Hümayunu",
      "-> Mustafa Reşid Paşa",
      "=> amaç: Avrupa burnunu sokmasın + reaya güvenliği",
      "=> can / mal / ırz + vergi adaleti + askerlik düzeni",
      "Islahat (1856) -> Kırım Savaşı sonrası, Paris’e jest",
      "=> gayrimüslimlere EK hak (Tanzimat’taki eşitliğin üstüne)",
      "I. Meşrutiyet 1876 ≠ II. Meşrutiyet 1908",
      "-> 1876 Kanun-i Esasi / Abdülhamid kısa süre sonra askıya alır",
    ],
    mnemonic: "T önce (39) → I sonra (56). Eşitlik Tanzimat’ta, ekstra Islahat’ta.",
    warning: "ÖSYM ‘ilk anayasa / eşitlik / Meşrutiyet yılı’nı karıştırır. 1876 ≠ 1908!",
    teacherNote: `${rankTitle}, 1856’ya kaydıysan sazan oldun. Tanzimat 39, Islahat 56 — deftere kırmızıyla yaz!`,
  };
}

export const SAMPLE_HISTORY_NOTE: HumanNoteCardProps = sampleHistoryNote("Acemi Tilki");
