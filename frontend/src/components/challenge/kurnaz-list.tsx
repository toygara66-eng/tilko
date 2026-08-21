"use client";

import { cn } from "@/lib/utils";
import type { KurnazEntry } from "@/lib/api";
import { PrizeBadge } from "@/components/challenge/prize-badge";

function formatMs(ms: number) {
  const total = Math.max(0, Math.floor(ms));
  const minutes = Math.floor(total / 60000);
  const seconds = Math.floor((total % 60000) / 1000);
  const milli = total % 1000;
  return `${minutes}:${seconds.toString().padStart(2, "0")}.${milli
    .toString()
    .padStart(3, "0")}`;
}

function badgeClass(badge: string) {
  if (badge === "fox") {
    return "badge-alfa font-semibold";
  }
  if (badge === "silver") {
    return "border-zinc-300 bg-zinc-200/80 text-zinc-800 dark:border-zinc-500 dark:bg-zinc-700/80 dark:text-zinc-100";
  }
  if (badge === "bronze") {
    return "border-amber-700/40 bg-amber-800/15 text-amber-800 dark:border-amber-500/40 dark:bg-amber-900/40 dark:text-amber-200";
  }
  return "border-orange-400/20 bg-orange-500/10 text-orange-800 dark:text-orange-200";
}

export function KurnazList({
  entries,
  highlightUserId,
  viewerRank,
  prizeBanner,
}: {
  entries: KurnazEntry[];
  highlightUserId?: string;
  viewerRank?: number | null;
  prizeBanner?: string;
}) {
  const banner =
    prizeBanner ||
    "Kürsü Ödülü: Ay sonunda ilk 3'e girenler sonraki ay BEDAVA Pro kazanıyor!";
  return (
    <div className="glow-orange rounded-2xl border border-orange-400/40 bg-white/70 p-4 backdrop-blur-xl dark:bg-zinc-950/55">
      <div className="mb-4 rounded-xl bg-gradient-to-r from-orange-600 via-orange-400 to-amber-300 px-3 py-2.5 text-[12px] font-semibold leading-snug text-zinc-950 shadow-[0_0_18px_rgba(251,146,60,0.45)]">
        {banner}
      </div>
      <div className="mb-4 flex items-end justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-orange-600 dark:text-orange-300">
            Hız sıralaması
          </p>
          <h3 className="mt-1 text-xl font-semibold tracking-tight text-zinc-900 dark:text-white">
            🏆 Kurnazlar Listesi
          </h3>
        </div>
        {viewerRank ? (
          <p className="rounded-full border border-orange-400/40 bg-orange-500/10 px-3 py-1 text-xs font-medium text-orange-800 dark:text-orange-200">
            Sıran #{viewerRank}
          </p>
        ) : null}
      </div>

      {entries.length === 0 ? (
        <p className="text-sm text-zinc-500">Henüz kurnaz yok. İlk tilki sen ol.</p>
      ) : (
        <ol className="space-y-2">
          {entries.map((entry) => {
            const mine = highlightUserId === entry.user_id;
            return (
              <li
                key={`${entry.rank}-${entry.user_id}`}
                className={cn(
                  "flex items-center justify-between gap-3 rounded-xl border px-3 py-2.5 backdrop-blur-md",
                  entry.badge === "fox"
                    ? "glow-orange border-orange-400/70 bg-orange-500/10"
                    : "border-zinc-200/80 bg-white/50 dark:border-zinc-800 dark:bg-zinc-900/40",
                  mine && "ring-1 ring-orange-400/70",
                )}
              >
                <div className="flex min-w-0 items-center gap-3">
                  <span className="w-6 font-mono text-sm text-zinc-500">
                    {entry.rank}
                  </span>
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-zinc-900 dark:text-zinc-100">
                      {entry.display_name}
                      {mine ? (
                        <span className="ml-2 text-[11px] text-orange-500">sen</span>
                      ) : null}
                    </p>
                    <div className="mt-1 flex flex-wrap items-center gap-1.5">
                      <span
                        className={cn(
                          "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px]",
                          badgeClass(entry.badge),
                        )}
                      >
                        {entry.emoji} {entry.title}
                      </span>
                      {entry.prize_badge ? <PrizeBadge label={entry.prize_badge} /> : null}
                    </div>
                  </div>
                </div>
                <span className="shrink-0 font-mono text-sm text-orange-700 dark:text-orange-300">
                  {formatMs(entry.time_spent_ms)}
                </span>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}

export { formatMs };
