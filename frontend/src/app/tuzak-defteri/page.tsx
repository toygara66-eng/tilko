"use client";

import { useEffect, useState } from "react";
import { HumanNoteCard } from "@/components/notes/human-note-card";
import { NoteModeToggle } from "@/components/notes/note-mode";
import { fromTrapItem } from "@/lib/note-format";
import { listTraps, type TrapItem } from "@/lib/api";
import { getUserId } from "@/lib/user";
import { useProfile } from "@/components/profile/profile-context";
import { PremiseAnalyzer } from "@/components/questions/premise-analyzer";
import { SolutionSteps } from "@/components/questions/solution-steps";

export default function TrapNotebookPage() {
  const { profile } = useProfile();
  const [traps, setTraps] = useState<TrapItem[]>([]);
  const [openId, setOpenId] = useState<number | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    listTraps(getUserId())
      .then((data) => setTraps(data.traps))
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Defter yüklenemedi"),
      );
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h1 className="font-scribble text-3xl text-amber-800 dark:text-amber-100 sm:text-4xl md:text-5xl">
            Tuzak Defteri
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-zinc-600 dark:text-zinc-400 sm:text-base">
            Çeldiriciye düşünce kenara kırmızı kalemle yazılmış analiz. Karta bas,
            reçete açılsın.
            {profile.weakTopics.length
              ? ` Zayıf alanların (${profile.weakTopics.join(", ")}) üstte.`
              : ""}
          </p>
        </div>
        <NoteModeToggle className="self-start" />
      </div>

      {error ? <p className="text-sm text-red-400">{error}</p> : null}

      {traps.length === 0 && !error ? (
        <HumanNoteCard
          variant="trap"
          title="Defter boş"
          tilt={-0.6}
          lines={[
            "-> henüz tuzak yok",
            "=> Dashboard’dan video analiz et",
            "=> yanlış şık -> buraya düşer",
          ]}
          warning="İlk yanlışın en değerli notun. Kaçırma."
        />
      ) : (
        <div
          className="protect-copy grid gap-8"
          onCopy={(event) => event.preventDefault()}
          onContextMenu={(event) => event.preventDefault()}
        >
          {traps.map((trap, index) => {
            const open = openId === trap.id;
            const card = fromTrapItem(trap, index % 2 === 0 ? -1 : 1);
            return (
                <div
                key={trap.id}
                role="button"
                tabIndex={0}
                onClick={() => setOpenId(open ? null : trap.id)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    setOpenId(open ? null : trap.id);
                  }
                }}
                className="block w-full min-w-0 text-left transition-transform duration-300 ease-out sm:hover:scale-[1.01]"
              >
                <HumanNoteCard
                  {...card}
                  lines={open ? card.lines : card.lines.slice(0, 2)}
                  warning={open ? card.warning : undefined}
                  mnemonic={open ? card.mnemonic : undefined}
                  footer={
                    open ? (
                      <div className="mt-4 space-y-3" onClick={(event) => event.stopPropagation()}>
                        <PremiseAnalyzer premises={trap.premises} reveal />
                        <SolutionSteps
                          steps={trap.step_by_step_solution}
                          tactic={trap.shortcut_tactic}
                        />
                      </div>
                    ) : undefined
                  }
                />
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
