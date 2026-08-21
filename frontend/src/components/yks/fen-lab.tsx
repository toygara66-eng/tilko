"use client";

import { Atom, Dna, FlaskConical } from "lucide-react";
import { cn } from "@/lib/utils";

export const FEN_BRANCHES = [
  {
    id: "fizik",
    label: "Fizik",
    subject: "TYT/AYT Fizik",
    Icon: Atom,
  },
  {
    id: "kimya",
    label: "Kimya",
    subject: "TYT/AYT Kimya",
    Icon: FlaskConical,
  },
  {
    id: "biyoloji",
    label: "Biyoloji",
    subject: "TYT/AYT Biyoloji",
    Icon: Dna,
  },
] as const;

export const FEN_TOPICS: Record<string, string[]> = {
  fizik: ["Hareket", "Kuvvet", "Enerji", "Elektrik", "Optik"],
  kimya: ["Atom", "Bağlar", "Asit-Baz", "Tepkimeler", "Çözeltiler"],
  biyoloji: ["Hücre", "Kalıtım", "Sistemler", "Ekosistem", "Enzim"],
};

export function FenLab({
  branch,
  topic,
  onBranch,
  onTopic,
}: {
  branch: string;
  topic: string;
  onBranch: (id: string, subject: string) => void;
  onTopic: (label: string) => void;
}) {
  const topics = branch ? FEN_TOPICS[branch] || [] : [];

  return (
    <div className="space-y-3 rounded-2xl border border-orange-400/30 bg-white/40 p-4 backdrop-blur-xl dark:bg-zinc-950/35">
      <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-orange-600 dark:text-orange-300">
        Fen Bilimleri Laboratuvarı
      </p>
      <div className="grid grid-cols-3 gap-2">
        {FEN_BRANCHES.map(({ id, label, subject, Icon }) => {
          const active = branch === id;
          return (
            <button
              key={id}
              type="button"
              onClick={() => onBranch(id, subject)}
              className={cn(
                "flex flex-col items-center gap-2 rounded-2xl border px-2 py-3 text-xs font-medium transition",
                active
                  ? "border-orange-400 bg-orange-500/15 text-orange-700 dark:text-orange-200"
                  : "border-zinc-200 bg-white/50 text-zinc-600 hover:border-orange-300 dark:border-zinc-800 dark:bg-zinc-900/40 dark:text-zinc-300",
              )}
            >
              <Icon className="h-5 w-5" />
              {label}
            </button>
          );
        })}
      </div>
      {topics.length ? (
        <div className="flex flex-wrap gap-2">
          {topics.map((label) => (
            <button
              key={label}
              type="button"
              onClick={() => onTopic(`${FEN_BRANCHES.find((item) => item.id === branch)?.subject} · ${label}`)}
              className={cn(
                "rounded-full border px-3 py-1 text-[11px] transition",
                topic.includes(label)
                  ? "border-orange-400 bg-orange-500/15 text-orange-700 dark:text-orange-200"
                  : "border-zinc-200 text-zinc-500 hover:border-orange-300 dark:border-zinc-700",
              )}
            >
              {label}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
