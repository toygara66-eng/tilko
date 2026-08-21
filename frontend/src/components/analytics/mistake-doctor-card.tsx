"use client";

import Link from "next/link";
import type { MistakeDoctorReport } from "@/lib/api";
import { cn } from "@/lib/utils";

const TONE: Record<string, string> = {
  "Dikkat hatası": "bg-amber-500",
  "Bilgi eksikliği": "bg-orange-500",
  "ÖSYM çeldirici tuzağı": "bg-red-500",
  "Süre tuzağı": "bg-cyan-500",
};

export function MistakeDoctorCard({
  report,
  loading,
  hideCta,
}: {
  report: MistakeDoctorReport | null;
  loading?: boolean;
  hideCta?: boolean;
}) {
  return (
    <section className="glow-orange relative overflow-hidden rounded-2xl border-2 border-orange-400/70 bg-white/60 p-5 backdrop-blur-xl dark:bg-zinc-950/50">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,_rgba(251,146,60,0.2),transparent_55%)]" />
      <div className="relative space-y-4">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-orange-600 dark:text-orange-300">
            Yanlış Analiz Doktoru
          </p>
          <h2 className="mt-1 text-lg font-semibold tracking-tight text-zinc-900 dark:text-white">
            Hata tipi teşhisi
          </h2>
        </div>

        {loading ? (
          <p className="text-sm text-zinc-500">Defter okunuyor…</p>
        ) : !report || report.trap_count === 0 ? (
          <div className="space-y-3">
            <p className="text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">
              {report?.summary ||
                "Tuzak Defteri boş. Analiz için birkaç yanlışın düşmesi lazım."}
            </p>
            {hideCta ? null : (
              <Link
                href="/analiz"
                className="inline-block text-sm text-orange-600 dark:text-orange-300"
              >
                Analize git
              </Link>
            )}
          </div>
        ) : (
          <>
            {report.dominant ? (
              <p className="font-mono text-2xl text-orange-600 dark:text-orange-300">
                {report.dominant} oranı: %{report.types[0]?.rate ?? 0}
              </p>
            ) : null}
            <p className="text-sm leading-relaxed text-zinc-700 dark:text-zinc-300">
              {report.summary}
            </p>
            <ul className="space-y-3">
              {report.types.map((item) => (
                <li key={item.type} className="space-y-1">
                  <div className="flex items-baseline justify-between gap-3 text-sm">
                    <span className="text-zinc-700 dark:text-zinc-200">
                      {item.type}
                    </span>
                    <span className="font-mono text-orange-600 dark:text-orange-300">
                      %{item.rate}
                    </span>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800">
                    <div
                      className={cn(
                        "h-full rounded-full shadow-[0_0_10px_rgba(251,146,60,0.45)]",
                        TONE[item.type] || "bg-orange-500",
                      )}
                      style={{ width: `${item.rate}%` }}
                    />
                  </div>
                </li>
              ))}
            </ul>
            {report.prescription ? (
              <p className="rounded-xl border border-orange-400/30 bg-orange-500/10 px-3 py-2 text-sm text-zinc-800 dark:text-orange-100">
                Reçete: {report.prescription}
              </p>
            ) : null}
            {report.weak_topics.length ? (
              <p className="text-xs text-zinc-500">
                Odak konular: {report.weak_topics.join(", ")}
              </p>
            ) : null}
          </>
        )}
      </div>
    </section>
  );
}
