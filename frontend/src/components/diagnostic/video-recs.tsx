"use client";

import type { RecommendedVideo } from "@/lib/api";

export function VideoRecs({ videos }: { videos: RecommendedVideo[] }) {
  if (!videos.length) return null;
  return (
    <div className="space-y-2">
      <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-orange-600 dark:text-orange-300">
        Zayıf alana göre ders
      </p>
      {videos.map((video) => (
        <a
          key={video.url}
          href={video.url}
          target="_blank"
          rel="noreferrer"
          className="block rounded-xl border border-orange-400/30 bg-orange-500/5 px-3 py-2 text-sm text-orange-800 backdrop-blur-md dark:text-orange-200"
        >
          {video.topic} · {video.title}
        </a>
      ))}
    </div>
  );
}
