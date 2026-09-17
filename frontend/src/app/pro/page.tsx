"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { ExternalLink, Loader2, RefreshCw, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PlayCheckoutModal } from "@/components/billing/play-checkout-modal";
import { useProfile } from "@/components/profile/profile-context";
import {
  hasNativePlayBilling,
  restorePlayPurchase,
} from "@/lib/billing";
import { verifySubscription } from "@/lib/api";
import { getUserId } from "@/lib/user";
import { PLAY_STORE_URL } from "@/lib/integrity";

function daysLeft(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const end = new Date(iso).getTime();
  if (!Number.isFinite(end)) return null;
  return Math.ceil((end - Date.now()) / (1000 * 60 * 60 * 24));
}

export default function ProPage() {
  const { profile, apply, refresh } = useProfile();
  const [payOpen, setPayOpen] = useState(false);
  const [restoreBusy, setRestoreBusy] = useState(false);
  const [restoreMsg, setRestoreMsg] = useState("");
  const [restoreErr, setRestoreErr] = useState("");
  const native = hasNativePlayBilling();
  const left = useMemo(
    () => daysLeft(profile.subscriptionExpiresAt),
    [profile.subscriptionExpiresAt],
  );
  const endingSoon =
    profile.isPremium && left !== null && left >= 0 && left <= 5;

  async function restore() {
    if (restoreBusy) return;
    setRestoreBusy(true);
    setRestoreErr("");
    setRestoreMsg("");
    try {
      if (!native) {
        throw new Error("Geri yükleme yalnızca Android uygulamasında çalışır.");
      }
      const receipt = await restorePlayPurchase("tilko_pro_monthly");
      await verifySubscription({
        user_id: getUserId(),
        product_id: receipt.productId,
        purchase_token: receipt.purchaseToken,
        order_id: receipt.orderId,
        platform: receipt.platform,
      });
      apply({ isPremium: true, isAdTier: false });
      setRestoreMsg("Abonelik geri yüklendi. Pro açık.");
      void refresh();
    } catch (err) {
      setRestoreErr(err instanceof Error ? err.message : "Geri yükleme başarısız");
    } finally {
      setRestoreBusy(false);
    }
  }

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
          Ödeme Google Play üzerinden. Pro’da kota yok, bekleme yok. Haftalık /
          aylık / yıllık paketler mağaza fiyatıyla alınır.
        </p>
        <ul className="mt-4 space-y-2 text-sm text-zinc-700 dark:text-zinc-300">
          <li>Sınırsız YouTube → not + ÖSYM sorusu</li>
          <li>Kota yok, bekleme yok</li>
          <li>Play aboneliği — iptal Play Store hesabından</li>
        </ul>

        {profile.isPremium ? (
          <div className="mt-5 rounded-2xl border border-emerald-400/40 bg-emerald-500/10 px-4 py-3">
            <p className="text-sm font-medium text-emerald-800 dark:text-emerald-200">
              Pro aktif
              {profile.subscriptionExpiresAt
                ? ` · bitiş ${new Date(profile.subscriptionExpiresAt).toLocaleDateString("tr-TR")}`
                : ""}
              {left !== null && left >= 0 ? ` · ${left} gün kaldı` : ""}
            </p>
            {endingSoon ? (
              <p className="mt-1 text-xs text-amber-700 dark:text-amber-300">
                Aboneliğin yakında bitiyor. Yenilemek için Play’den devam et veya
                aşağıdan geri yükle.
              </p>
            ) : null}
          </div>
        ) : null}

        {!native ? (
          <div className="mt-5 rounded-2xl border border-orange-400/40 bg-orange-500/10 px-4 py-3 text-sm text-zinc-700 dark:text-zinc-300">
            Gerçek ödeme yalnızca Android uygulamasında. Web’den Play Store’a
            geçip Tilko’yu aç, sonra Pro’ya geç.
          </div>
        ) : null}

        <div className="mt-6 flex flex-wrap gap-3">
          {profile.isPremium ? (
            <Button size="lg" className="h-12" disabled>
              Pro aktif
            </Button>
          ) : native ? (
            <Button size="lg" className="h-12" onClick={() => setPayOpen(true)}>
              <Sparkles className="h-4 w-4" />
              Tilko Pro&apos;ya Geç
            </Button>
          ) : (
            <Button asChild size="lg" className="h-12">
              <a href={PLAY_STORE_URL} target="_blank" rel="noreferrer">
                <ExternalLink className="h-4 w-4" />
                Play Store’dan aç
              </a>
            </Button>
          )}
          <Button asChild variant="outline" size="lg" className="h-12">
            <Link href="/analiz">Analize dön</Link>
          </Button>
        </div>

        <div className="mt-4 flex flex-col gap-2">
          {native ? (
            <Button
              type="button"
              variant="outline"
              className="h-11 w-full"
              disabled={restoreBusy}
              onClick={() => void restore()}
            >
              {restoreBusy ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <RefreshCw className="h-4 w-4" />
              )}
              Satın almayı geri yükle
            </Button>
          ) : (
            <Button asChild variant="outline" className="h-11 w-full">
              <a href={PLAY_STORE_URL} target="_blank" rel="noreferrer">
                Google Play’de Tilko
              </a>
            </Button>
          )}
          {restoreMsg ? (
            <p className="text-sm text-emerald-700 dark:text-emerald-300">{restoreMsg}</p>
          ) : null}
          {restoreErr ? <p className="text-sm text-red-500">{restoreErr}</p> : null}
        </div>
      </section>
      <PlayCheckoutModal open={payOpen} onClose={() => setPayOpen(false)} />
    </div>
  );
}
