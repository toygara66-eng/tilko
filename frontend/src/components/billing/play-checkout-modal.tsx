"use client";

import { useEffect, useState } from "react";
import { Loader2, ShieldCheck, Sparkles, Tag, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useProfile } from "@/components/profile/profile-context";
import {
  applyPromo,
  getSubscriptionStatus,
  verifySubscription,
  type PromoQuote,
  type SubscriptionPlan,
  type SubscriptionStatus,
} from "@/lib/api";
import { FALLBACK_PLANS, hasNativePlayBilling, launchPlayPurchase } from "@/lib/billing";
import { getUserId } from "@/lib/user";
import { cn } from "@/lib/utils";

function lira(amount: number) {
  const rounded = Math.round(amount * 100) / 100;
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(2);
}

export function PlayCheckoutModal({
  open,
  onClose,
  onActivated,
}: {
  open: boolean;
  onClose: () => void;
  onActivated?: (status: SubscriptionStatus) => void;
}) {
  const { profile, apply, refresh } = useProfile();
  const [plans, setPlans] = useState<SubscriptionPlan[]>(FALLBACK_PLANS);
  const [sandbox, setSandbox] = useState(true);
  const [sku, setSku] = useState(FALLBACK_PLANS[0].id);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [phase, setPhase] = useState<"pick" | "sheet" | "done">("pick");
  const [promoInput, setPromoInput] = useState("");
  const [promoBusy, setPromoBusy] = useState(false);
  const [promoError, setPromoError] = useState("");
  const [quote, setQuote] = useState<PromoQuote | null>(null);

  useEffect(() => {
    if (!open) return;
    setError("");
    setBusy(false);
    setPromoInput("");
    setPromoError("");
    setQuote(null);
    setPhase(profile.isPremium ? "done" : "pick");
    getSubscriptionStatus(getUserId())
      .then((data) => {
        if (data.plans?.length) setPlans(data.plans);
        setSandbox(Boolean(data.sandbox));
        if (data.is_premium) setPhase("done");
      })
      .catch(() => setPlans(FALLBACK_PLANS));
  }, [open, profile.isPremium]);

  if (!open) return null;

  const selected = plans.find((item) => item.id === sku) || plans[0];
  const native = hasNativePlayBilling();
  const payable =
    quote && quote.product_id === sku ? quote.payable_amount : selected?.price_try;

  async function applyCode() {
    if (promoBusy) return;
    setPromoBusy(true);
    setPromoError("");
    try {
      const data = await applyPromo({
        user_id: getUserId(),
        code: promoInput,
        product_id: sku,
      });
      setQuote(data);
    } catch (err) {
      setQuote(null);
      setPromoError(err instanceof Error ? err.message : "Kupon uygulanamadı");
    } finally {
      setPromoBusy(false);
    }
  }

  async function pay() {
    if (!selected || busy) return;
    setBusy(true);
    setError("");
    setPhase("sheet");
    try {
      const receipt = await launchPlayPurchase(getUserId(), selected.id);
      const data = await verifySubscription({
        user_id: getUserId(),
        product_id: receipt.productId,
        purchase_token: receipt.purchaseToken,
        order_id: receipt.orderId,
        platform: receipt.platform,
      });
      apply({ isPremium: true, isAdTier: false });
      setPhase("done");
      onActivated?.(data);
      void refresh();
    } catch (err) {
      setPhase("pick");
      setError(err instanceof Error ? err.message : "Ödeme doğrulanamadı");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-zinc-950/70 p-0 backdrop-blur-sm sm:items-center sm:p-4">
      <div className="glow-orange relative w-full max-w-md overflow-hidden rounded-t-3xl border-2 border-orange-400/80 bg-white/90 p-6 backdrop-blur-xl dark:bg-zinc-950/90 sm:rounded-3xl">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top,_rgba(251,146,60,0.22),transparent_60%)]" />
        <button
          type="button"
          onClick={onClose}
          className="absolute right-4 top-4 z-10 rounded-full p-1 text-zinc-500 hover:bg-zinc-200/70 dark:hover:bg-zinc-800"
          aria-label="Kapat"
        >
          <X className="h-4 w-4" />
        </button>
        <div className="relative space-y-4">
          <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-orange-600 dark:text-orange-300">
            {native ? "Google Play" : "Google Play · test"}
          </p>
          <h2 className="text-2xl font-semibold tracking-tight text-zinc-900 dark:text-white">
            Tilko Pro
          </h2>

          {phase === "done" || profile.isPremium ? (
            <div className="space-y-3">
              <p className="flex items-center gap-2 text-sm text-emerald-700 dark:text-emerald-300">
                <ShieldCheck className="h-4 w-4" />
                Abonelik doğrulandı. Kota kalktı.
              </p>
              <Button type="button" className="h-11 w-full" onClick={onClose}>
                Devam et
              </Button>
            </div>
          ) : (
            <>
              <p className="text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">
                Hey {profile.title}, Play Billing fişini sunucu{" "}
                <span className="font-mono text-xs">/subscription/verify</span> ile
                doğrular. {sandbox ? "Şu an test ortamı — gerçek kart çekilmez." : "Canlı Play token gerekli."}
              </p>
              <div className="grid gap-2">
                {plans.map((plan) => (
                  <button
                    key={plan.id}
                    type="button"
                    onClick={() => {
                      setSku(plan.id);
                      if (!quote?.code) return;
                      applyPromo({
                        user_id: getUserId(),
                        code: quote.code,
                        product_id: plan.id,
                      })
                        .then((data) => {
                          setQuote(data);
                          setPromoError("");
                        })
                        .catch((err) =>
                          setPromoError(
                            err instanceof Error ? err.message : "Kupon yenilenemedi",
                          ),
                        );
                    }}
                    className={cn(
                      "rounded-2xl border px-4 py-3 text-left transition",
                      sku === plan.id
                        ? "border-orange-400 bg-orange-500/15"
                        : "border-zinc-200 bg-white/50 hover:border-orange-300 dark:border-zinc-800 dark:bg-zinc-900/40",
                    )}
                  >
                    <span className="block text-sm font-semibold text-zinc-900 dark:text-white">
                      {plan.label}
                    </span>
                    <span className="text-xs text-zinc-500">{plan.price_label}</span>
                  </button>
                ))}
              </div>

              <div className="space-y-2">
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                  İndirim kodu
                </p>
                <div className="flex gap-2">
                  <Input
                    value={promoInput}
                    onChange={(event) => setPromoInput(event.target.value.toUpperCase())}
                    placeholder="TILKO20"
                    className="h-11 font-mono tracking-wide"
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        event.preventDefault();
                        void applyCode();
                      }
                    }}
                  />
                  <Button
                    type="button"
                    variant="outline"
                    className="h-11 shrink-0"
                    disabled={promoBusy || !promoInput.trim()}
                    onClick={() => void applyCode()}
                  >
                    {promoBusy ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Tag className="h-4 w-4" />
                    )}
                    Uygula
                  </Button>
                </div>
                {promoError ? <p className="text-sm text-red-500">{promoError}</p> : null}
                {quote?.classroom_joined && quote.join_message ? (
                  <div className="rounded-2xl border border-emerald-400/50 bg-emerald-500/10 px-4 py-3">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-emerald-700 dark:text-emerald-300">
                      Sınıfa katıldın
                    </p>
                    <p className="mt-1 text-sm leading-relaxed text-emerald-900 dark:text-emerald-100">
                      {quote.join_message}
                    </p>
                  </div>
                ) : null}
              </div>

              <div className="rounded-2xl border border-orange-400/40 bg-orange-500/10 px-4 py-3">
                <p className="text-[10px] uppercase tracking-[0.2em] text-orange-600 dark:text-orange-300">
                  Ödenecek tutar
                </p>
                {quote && quote.product_id === sku ? (
                  <div className="mt-1 space-y-1">
                    <p className="text-xs text-zinc-500 line-through">
                      {lira(quote.original_price)} TL
                    </p>
                    <p className="text-lg font-semibold text-emerald-700 dark:text-emerald-300">
                      {lira(payable ?? 0)} TL
                    </p>
                    <p className="text-sm text-emerald-800 dark:text-emerald-200">
                      {quote.message}
                    </p>
                  </div>
                ) : (
                  <p className="mt-1 text-lg font-semibold text-zinc-900 dark:text-white">
                    {selected?.price_label}
                  </p>
                )}
              </div>

              {phase === "sheet" ? (
                <div className="rounded-2xl border border-orange-400/40 bg-zinc-950 px-4 py-3 text-sm text-zinc-100">
                  <p className="text-[10px] uppercase tracking-[0.2em] text-orange-300">
                    Play Billing
                  </p>
                  <p className="mt-1 font-medium">{selected?.label}</p>
                  <p className="text-xs text-zinc-400">
                    {quote && quote.product_id === sku
                      ? `${lira(quote.payable_amount)} TL`
                      : selected?.price_label}
                  </p>
                </div>
              ) : null}
              {error ? <p className="text-sm text-red-500">{error}</p> : null}
              <div className="flex gap-2">
                <Button
                  type="button"
                  className="h-11 flex-1"
                  disabled={busy}
                  onClick={() => void pay()}
                >
                  {busy ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Sparkles className="h-4 w-4" />
                  )}
                  {native ? "Play ile satın al" : "Test satın al"}
                </Button>
                <Button type="button" variant="outline" className="h-11" onClick={onClose}>
                  Vazgeç
                </Button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
