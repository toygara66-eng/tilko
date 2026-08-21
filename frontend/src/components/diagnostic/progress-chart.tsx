"use client";

import type { ProgressPoint } from "@/lib/api";

export function ProgressChart({ points }: { points: ProgressPoint[] }) {
  if (points.length === 0) {
    return (
      <p className="text-sm text-zinc-500">Henüz check-up yok. İlk teşhis grafiğin ilk noktası.</p>
    );
  }

  const width = 320;
  const height = 120;
  const pad = 16;
  const scores = points.map((point) => point.score);
  const min = Math.min(0, ...scores);
  const max = Math.max(100, ...scores);
  const span = max - min || 1;
  const coords = points.map((point, index) => {
    const x =
      points.length === 1
        ? width / 2
        : pad + ((width - pad * 2) * index) / (points.length - 1);
    const y = height - pad - ((point.score - min) / span) * (height - pad * 2);
    return { x, y, point };
  });
  const line = coords.map((item) => `${item.x},${item.y}`).join(" ");

  return (
    <div className="space-y-2">
      <svg viewBox={`0 0 ${width} ${height}`} className="h-32 w-full overflow-visible">
        <polyline
          fill="none"
          stroke="rgb(251 146 60 / 0.25)"
          strokeWidth="8"
          points={line}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
        <polyline
          fill="none"
          stroke="#f97316"
          strokeWidth="2.5"
          points={line}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
        {coords.map((item) => (
          <circle
            key={item.point.date}
            cx={item.x}
            cy={item.y}
            r="4"
            fill="#f97316"
            className="drop-shadow-[0_0_8px_rgba(249,115,22,0.8)]"
          />
        ))}
      </svg>
      <div className="flex justify-between text-[11px] text-zinc-500">
        {points.map((point) => (
          <span key={point.date}>
            {point.date.slice(5)} · {Math.round(point.score)}
          </span>
        ))}
      </div>
    </div>
  );
}
