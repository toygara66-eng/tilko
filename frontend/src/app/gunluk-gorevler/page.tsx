"use client";

import { useEffect, useMemo, useState } from "react";
import { Timer } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { completeTrap, dailyMissions, type TrapItem } from "@/lib/api";
import { getUserId } from "@/lib/user";
import { useProfile } from "@/components/profile/profile-context";
import { ReportQuestionControl } from "@/components/questions/report-question";
import { PremiseAnalyzer } from "@/components/questions/premise-analyzer";
import { SolutionSteps } from "@/components/questions/solution-steps";

export default function DailyMissionsPage() {
  const { refresh } = useProfile();
  const [traps, setTraps] = useState<TrapItem[]>([]);
  const [active, setActive] = useState<TrapItem | null>(null);
  const [seconds, setSeconds] = useState(0);
  const [running, setRunning] = useState(false);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    dailyMissions(getUserId())
      .then((data) => {
        setTraps(data.traps);
        setError("");
      })
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Görevler yüklenemedi"),
      );
  }, []);

  useEffect(() => {
    if (!running) return;
    const id = window.setInterval(() => setSeconds((n) => n + 1), 1000);
    return () => window.clearInterval(id);
  }, [running]);

  const overTime = seconds >= 60;
  const clock = useMemo(() => {
    const m = Math.floor(seconds / 60)
      .toString()
      .padStart(2, "0");
    const s = (seconds % 60).toString().padStart(2, "0");
    return `${m}:${s}`;
  }, [seconds]);

  function startFocus(trap: TrapItem) {
    setActive(trap);
    setSeconds(0);
    setRunning(true);
    setMsg("");
  }

  async function answer(letter: string) {
    if (!active || busy) return;
    setRunning(false);
    setBusy(true);
    try {
      const res = await completeTrap({
        user_id: getUserId(),
        trap_id: active.id,
        chosen: letter,
      });
      setMsg(res.message);
      const remaining = await dailyMissions(getUserId());
      setTraps(remaining.traps);
      setError("");
      if (res.correct) {
        setActive(null);
        void refresh();
      }
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Cevap gönderilemedi.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight md:text-4xl">
          Günlük Görevler
        </h1>
        <p className="mt-2 max-w-2xl text-zinc-600 dark:text-zinc-400">
          Ebbinghaus unutma eğrisine göre bugün çözmen gereken tuzaklar. Odak
          modunda 60 saniyeyi geçme.
        </p>
        {error ? (
          <p className="mt-2 text-sm text-red-500">{error}</p>
        ) : null}
      </div>

      <Card className="border-cyan-400/20">
        <CardContent className="flex items-center justify-between py-6">
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-zinc-500">
              Odaklanma
            </p>
            <p
              className={`mt-1 font-mono text-5xl ${overTime ? "text-red-500" : "text-cyan-700 dark:text-cyan-300"}`}
            >
              {clock}
            </p>
            {overTime ? (
              <p className="mt-1 text-sm text-amber-300">
                ÖSYM seni 60 saniyeden fazla oyaladı.
              </p>
            ) : null}
          </div>
          <Timer className="h-10 w-10 text-cyan-400" />
        </CardContent>
      </Card>

      {active ? (
        <Card>
          <CardContent
            className="protect-copy space-y-4"
            onCopy={(event) => event.preventDefault()}
            onContextMenu={(event) => event.preventDefault()}
          >
            <div className="flex items-start justify-between gap-3">
              <Badge>{active.topic || "Tekrar"}</Badge>
              <ReportQuestionControl
                questionId={active.question_id || `trap:${active.id}`}
              />
            </div>
            <p className="text-lg text-zinc-800 dark:text-zinc-100">{active.question_text}</p>
            {active.misconception_tag ? (
              <Badge className="border-orange-400/50 bg-orange-500/10 text-orange-700 dark:text-orange-200">
                {active.misconception_tag}
              </Badge>
            ) : null}
            <PremiseAnalyzer premises={active.premises} reveal={Boolean(msg)} />
            <div className="grid gap-2">
              {Object.entries(active.options || {}).map(([letter, text]) => (
                <Button
                  key={letter}
                  variant="outline"
                  className="h-auto justify-start whitespace-normal py-3 text-left"
                  onClick={() => answer(letter)}
                  disabled={busy}
                >
                  <span className="text-cyan-400">{letter})</span> {text}
                </Button>
              ))}
            </div>
            {msg ? <p className="text-sm text-zinc-400">{msg}</p> : null}
            {msg ? (
              <SolutionSteps
                steps={active.step_by_step_solution}
                tactic={active.shortcut_tactic}
              />
            ) : null}
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-3">
          {traps.length === 0 ? (
            <Card>
              <CardContent className="py-10 text-center text-sm text-zinc-500">
                Bugün vadesi gelen tuzak yok. Defter temiz.
              </CardContent>
            </Card>
          ) : (
            traps.map((trap) => (
              <Card key={trap.id}>
                <CardContent className="flex items-center justify-between gap-4">
                  <div>
                    <p className="text-sm text-zinc-800 dark:text-zinc-100">{trap.question_text}</p>
                    <p className="mt-1 text-xs text-zinc-500">
                      {trap.topic || "Konu yok"} · tekrar {trap.review_count}
                    </p>
                  </div>
                  <Button onClick={() => startFocus(trap)}>Odaklan</Button>
                </CardContent>
              </Card>
            ))
          )}
        </div>
      )}
    </div>
  );
}
