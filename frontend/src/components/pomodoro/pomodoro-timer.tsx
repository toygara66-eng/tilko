"use client";

import { Pause, Play, ShieldAlert } from "lucide-react";
import { usePenalty } from "@/components/pomodoro/penalty-context";
import { usePomodoro } from "@/components/pomodoro/pomodoro-context";
import { useProfile } from "@/components/profile/profile-context";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

const PRESETS = [
  { label: "1 dk", seconds: 60 },
  { label: "25 dk", seconds: 25 * 60 },
  { label: "45 dk", seconds: 45 * 60 },
];

function formatClock(total: number) {
  const m = Math.floor(total / 60)
    .toString()
    .padStart(2, "0");
  const s = (total % 60).toString().padStart(2, "0");
  return `${m}:${s}`;
}

export function PomodoroTimer({
  compact = false,
  hero = false,
}: {
  compact?: boolean;
  hero?: boolean;
}) {
  const { isPenalized } = usePenalty();
  const { duration, remaining, running, done, start, pause, choose } =
    usePomodoro();
  const { profile } = useProfile();

  return (
    <Card className={cn("border-orange-400/30", compact && "p-0", hero && "glow-orange border-orange-400/70")}>
      <CardContent className={cn("space-y-4", compact ? "p-3" : hero ? "py-8" : "py-6")}>
        <div className="flex items-center justify-between gap-2">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-orange-600 dark:text-orange-300">
            Pomodoro
          </p>
          <ShieldAlert className="h-5 w-5 shrink-0 text-red-400" />
        </div>

        <p
          className={cn(
            "font-mono text-orange-600 dark:text-orange-300",
            compact ? "text-3xl" : hero ? "text-6xl" : "text-5xl",
          )}
        >
          {formatClock(remaining)}
        </p>

        <div className="flex flex-wrap gap-2">
          {PRESETS.map((preset) => (
            <button
              key={preset.seconds}
              type="button"
              disabled={running}
              onClick={() => choose(preset.seconds)}
              className={cn(
                "rounded-full border px-3 py-1 text-xs",
                duration === preset.seconds
                  ? "border-orange-500 bg-orange-500/10 text-orange-800 dark:text-orange-200"
                  : "border-zinc-300 text-zinc-600 hover:border-zinc-400 dark:border-zinc-700 dark:text-zinc-400 dark:hover:border-zinc-500",
                running && "opacity-50",
              )}
            >
              {preset.label}
            </button>
          ))}
        </div>

        <div className="flex gap-2">
          {running ? (
            <Button variant="outline" onClick={pause} className="flex-1">
              <Pause className="h-4 w-4" />
              Duraklat
            </Button>
          ) : (
            <Button onClick={start} disabled={isPenalized} className="flex-1">
              <Play className="h-4 w-4" />
              Başlat
            </Button>
          )}
        </div>

        {done ? (
          <p className="text-sm text-orange-600 dark:text-orange-300">
            Helal olsun {profile.title}, seans bitti.
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}
