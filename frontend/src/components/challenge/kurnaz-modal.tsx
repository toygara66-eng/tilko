"use client";

import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { KurnazList } from "@/components/challenge/kurnaz-list";
import { getKurnazLeaderboard, type KurnazEntry } from "@/lib/api";
import { getUserId } from "@/lib/user";

export function KurnazModal({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const [entries, setEntries] = useState<KurnazEntry[]>([]);
  const [rank, setRank] = useState<number | null>(null);
  const [userId, setUserId] = useState("");
  const [banner, setBanner] = useState(
    "Kürsü Ödülü: Ay sonunda ilk 3'e girenler sonraki ay BEDAVA Pro kazanıyor!",
  );

  useEffect(() => {
    if (!open) return;
    const id = getUserId();
    setUserId(id);
    getKurnazLeaderboard(id)
      .then((data) => {
        setEntries(data.entries);
        setRank(data.viewer_rank);
        if (data.prize_banner) setBanner(data.prize_banner);
      })
      .catch(() => {
        setEntries([]);
        setRank(null);
      });
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="kurnaz-title"
      className="fixed inset-0 z-[80] flex items-center justify-center p-4"
    >
      <button
        type="button"
        aria-label="Kapat"
        className="absolute inset-0 bg-zinc-950/55 backdrop-blur-sm"
        onClick={onClose}
      />
      <div className="relative w-full max-w-lg">
        <button
          type="button"
          onClick={onClose}
          className="absolute -right-1 -top-10 rounded-full p-2 text-zinc-200 hover:bg-white/10"
          aria-label="Listeyi kapat"
        >
          <X className="h-5 w-5" />
        </button>
        <div id="kurnaz-title">
          <KurnazList
            entries={entries}
            highlightUserId={userId}
            viewerRank={rank}
            prizeBanner={banner}
          />
        </div>
      </div>
    </div>
  );
}
