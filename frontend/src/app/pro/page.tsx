"use client";

import { useState } from "react";
import Link from "next/link";
import { Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PlayCheckoutModal } from "@/components/billing/play-checkout-modal";
import { useProfile } from "@/components/profile/profile-context";

export default function ProPage() {
  const { profile } = useProfile();
  const [payOpen, setPayOpen] = useState(false);

  return (
    <div className="mx-auto max-w-lg space-y-6">
      <section className="glow-orange rounded-2xl border-2 border-orange-400/70 bg-white/60 p-6 backdrop-blur-xl dark:bg-zinc-950/50">
        <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-orange-600 dark:text-orange-300">
          Tilko Pro
        </p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-zinc-900 dark:text-white">
          Hey {profile.title}, sınırsız ders analizi
        </h1>
        <p className="mt-3 text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">
          Deneme 7 gün. Bitince silme — reklamlı ücretsiz modda günde 1 kısa
          video kalır. Pro’da süre yok, kota yok. Ödeme Google Play Billing ile
          (veya test ortamında) doğrulanır.
        </p>
        <ul className="mt-4 space-y-2 text-sm text-zinc-700 dark:text-zinc-300">
          <li>Sınırsız YouTube → not + ÖSYM sorusu</li>
          <li>Kota yok, bekleme yok</li>
          <li>Aylık Sazan Avı indirimleri Pro’ya eklenir</li>
        </ul>
        <div className="mt-6 flex flex-wrap gap-3">
          {profile.isPremium ? (
            <Button size="lg" className="h-12" disabled>
              Pro aktif
            </Button>
          ) : (
            <Button size="lg" className="h-12" onClick={() => setPayOpen(true)}>
              <Sparkles className="h-4 w-4" />
              Tilko Pro&apos;ya Geç
            </Button>
          )}
          <Button asChild variant="outline" size="lg" className="h-12">
            <Link href="/analiz">Analize dön</Link>
          </Button>
        </div>
      </section>
      <PlayCheckoutModal open={payOpen} onClose={() => setPayOpen(false)} />
    </div>
  );
}
