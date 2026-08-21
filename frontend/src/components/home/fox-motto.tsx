"use client";

import { useEffect, useState } from "react";
import { getMotivationalQuote } from "@/lib/api";
import { getUserId } from "@/lib/user";
import { useProfile } from "@/components/profile/profile-context";

export function FoxMotto() {
  const { profile, ready } = useProfile();
  const [quote, setQuote] = useState("");

  useEffect(() => {
    if (!ready || !profile.isOnboarded) return;
    getMotivationalQuote(getUserId())
      .then((data) => setQuote(data.quote))
      .catch(() => setQuote(""));
  }, [ready, profile.isOnboarded, profile.title, profile.examTarget]);

  if (!quote) return null;

  return (
    <p className="px-1 text-center text-[13px] leading-relaxed text-zinc-500 dark:text-zinc-400">
      <span className="mr-1.5 text-orange-500/80">🦊</span>
      <span className="italic">{quote}</span>
    </p>
  );
}
