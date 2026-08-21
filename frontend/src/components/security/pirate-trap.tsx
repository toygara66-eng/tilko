"use client";

import { TilkoLogo } from "@/components/brand/tilko-logo";
import { Button } from "@/components/ui/button";
import { openOfficialPlayStore } from "@/lib/integrity";

function FoxMascot() {
  return (
    <svg
      viewBox="0 0 120 120"
      className="mx-auto h-28 w-28 drop-shadow-[0_0_28px_rgba(249,115,22,0.75)]"
      aria-hidden
    >
      <circle cx="60" cy="60" r="56" fill="#18181b" stroke="#f97316" strokeWidth="3" />
      <path d="M22 48 L42 18 L52 46 Z" fill="#f97316" />
      <path d="M98 48 L78 18 L68 46 Z" fill="#f97316" />
      <ellipse cx="60" cy="68" rx="32" ry="28" fill="#fb923c" />
      <ellipse cx="60" cy="78" rx="16" ry="12" fill="#fff7ed" />
      <circle cx="48" cy="64" r="5" fill="#09090b" />
      <circle cx="72" cy="64" r="5" fill="#09090b" />
      <path d="M60 72 L56 78 L64 78 Z" fill="#ea580c" />
    </svg>
  );
}

export function PirateTrap() {
  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-zinc-950 px-4">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top,_rgba(249,115,22,0.28),transparent_55%)]" />
      <section className="relative w-full max-w-md rounded-3xl border border-orange-400/55 bg-zinc-950/70 p-6 text-center shadow-[0_0_48px_rgba(249,115,22,0.28)] backdrop-blur-xl">
        <div className="mb-4 flex justify-center">
          <TilkoLogo size={44} />
        </div>
        <FoxMascot />
        <h1 className="mt-4 text-2xl font-semibold leading-snug tracking-tight text-orange-400">
          Uf, Sazan Gibi Atladın Yavru Kurt! 🦊
        </h1>
        <p className="mt-3 text-sm leading-relaxed text-zinc-300">
          Kaçak yollardan ormana girmeye çalıştığını fark ettik. Bu APK bayat
          çıktı! Tilko&apos;nun tüm yapay zeka güçlerinden güvenle yararlanmak
          için resmi Google Play kovanımıza dön.
        </p>
        <Button
          type="button"
          size="lg"
          onClick={openOfficialPlayStore}
          className="mt-6 h-12 w-full bg-orange-500 text-zinc-950 shadow-[0_0_24px_rgba(249,115,22,0.55)] hover:bg-orange-400"
        >
          Google Play&apos;e Git
        </Button>
      </section>
    </div>
  );
}
