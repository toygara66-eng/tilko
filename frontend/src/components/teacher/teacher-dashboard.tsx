"use client";

import { useEffect, useState } from "react";
import { Loader2, LogOut, Send, Tag, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { MistakeDoctorCard } from "@/components/analytics/mistake-doctor-card";
import {
  createTeacherPromo,
  getTeacherClassroom,
  getTeacherStudentAnalysis,
  listTeacherPromos,
  shareTeacherResource,
  type PromoCoupon,
  type TeacherClassroom,
  type TeacherStudentAnalysis,
  type TeacherStudentCard,
} from "@/lib/api";
import { logout } from "@/lib/auth";
import { cn } from "@/lib/utils";

function medal(rank: number) {
  if (rank === 1) return "1";
  if (rank === 2) return "2";
  if (rank === 3) return "3";
  return String(rank);
}

export function TeacherDashboard() {
  const [room, setRoom] = useState<TeacherClassroom | null>(null);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<string>("");
  const [analysis, setAnalysis] = useState<TeacherStudentAnalysis | null>(null);
  const [analysisBusy, setAnalysisBusy] = useState(false);
  const [coupons, setCoupons] = useState<PromoCoupon[]>([]);

  async function load() {
    setError("");
    try {
      const data = await getTeacherClassroom();
      setRoom(data);
      const promo = await listTeacherPromos().catch(() => ({ coupons: [] }));
      setCoupons(promo.coupons || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sınıf yüklenemedi");
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function openStudent(studentId: string) {
    setSelected(studentId);
    setAnalysisBusy(true);
    try {
      setAnalysis(await getTeacherStudentAnalysis(studentId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Analiz alınamadı");
    } finally {
      setAnalysisBusy(false);
    }
  }

  const hot = room?.hot_topics || [];
  const ranking = room?.ranking || [];

  return (
    <div className="mx-auto w-full max-w-5xl space-y-6 pb-10">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-orange-600 dark:text-orange-300">
            Hoca kontrol paneli
          </p>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight text-zinc-900 dark:text-white">
            {room?.teacher_name || "Kürsü"}
          </h1>
          <p className="mt-1 text-sm text-zinc-500">
            {room
              ? `${room.student_count} öğrenci · sınıf ortalaması ${room.class_average}`
              : "Sınıf yükleniyor…"}
          </p>
        </div>
        <Button
          type="button"
          variant="outline"
          onClick={() => {
            logout();
            window.location.assign("/giris/");
          }}
        >
          <LogOut className="h-4 w-4" />
          Çıkış
        </Button>
      </header>

      {error ? <p className="text-sm text-red-500">{error}</p> : null}

      <section className="grid gap-4 lg:grid-cols-5">
        <article className="glow-orange rounded-2xl border-2 border-orange-400/60 bg-white/70 p-5 backdrop-blur-xl lg:col-span-3 dark:bg-zinc-950/50">
          <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-orange-600">
            Kürsü
          </p>
          <h2 className="mt-1 text-lg font-semibold text-zinc-900 dark:text-white">
            Net sıralaması
          </h2>
          <ol className="mt-4 space-y-2">
            {ranking.length === 0 ? (
              <li className="text-sm text-zinc-500">
                Henüz öğrenci yok. Sınıf kuponu üret, öğrenciler kodu uygulayınca buraya düşer.
              </li>
            ) : (
              ranking.map((student) => (
                <li key={student.user_id}>
                  <button
                    type="button"
                    onClick={() => void openStudent(student.user_id)}
                    className={cn(
                      "flex w-full items-center gap-3 rounded-xl border px-3 py-2.5 text-left transition",
                      selected === student.user_id
                        ? "border-orange-400 bg-orange-500/15"
                        : "border-zinc-200 bg-white/60 hover:border-orange-300 dark:border-zinc-800 dark:bg-zinc-950/40",
                    )}
                  >
                    <span className="flex h-8 w-8 items-center justify-center rounded-full bg-zinc-900 text-xs font-bold text-orange-300">
                      {medal(student.rank)}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-semibold text-zinc-900 dark:text-white">
                        {student.display_name}
                      </span>
                      <span className="text-[11px] text-zinc-500">
                        {student.net_range || "net yok"} · {student.trap_count} tuzak
                      </span>
                    </span>
                    <span className="font-mono text-sm text-orange-600">
                      {student.baseline_score.toFixed(1)}
                    </span>
                  </button>
                </li>
              ))
            )}
          </ol>
        </article>

        <article className="rounded-2xl border border-zinc-200 bg-white/70 p-5 backdrop-blur-xl lg:col-span-2 dark:border-zinc-800 dark:bg-zinc-950/50">
          <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-orange-600">
            Hata dağılımı
          </p>
          <h2 className="mt-1 text-lg font-semibold text-zinc-900 dark:text-white">
            Sıcaklık haritası
          </h2>
          <p className="mt-1 text-xs text-zinc-500">
            Sınıfın en çok zorlandığı 5 konu — derste bunları tekrar et.
          </p>
          <ul className="mt-4 space-y-3">
            {hot.length === 0 ? (
              <li className="text-sm text-zinc-500">Yeterli tuzak verisi yok.</li>
            ) : (
              hot.map((item) => (
                <li key={item.topic}>
                  <div className="mb-1 flex justify-between text-sm">
                    <span className="text-zinc-800 dark:text-zinc-200">{item.topic}</span>
                    <span className="font-mono text-xs text-zinc-500">{item.hits}</span>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-amber-400 to-red-500"
                      style={{ width: `${Math.max(item.intensity, 8)}%` }}
                    />
                  </div>
                </li>
              ))
            )}
          </ul>
        </article>
      </section>

      <section className="rounded-2xl border border-zinc-200 bg-white/70 p-5 backdrop-blur-xl dark:border-zinc-800 dark:bg-zinc-950/50">
        <div className="flex items-center gap-2">
          <Users className="h-4 w-4 text-orange-500" />
          <h2 className="text-lg font-semibold text-zinc-900 dark:text-white">Öğrencilerim</h2>
        </div>
        <div className="mt-4 grid gap-2 sm:grid-cols-2">
          {(room?.students || []).map((student) => (
            <StudentChip
              key={student.user_id}
              student={student}
              active={selected === student.user_id}
              onOpen={() => void openStudent(student.user_id)}
            />
          ))}
        </div>
        {analysisBusy ? (
          <p className="mt-4 flex items-center gap-2 text-sm text-zinc-500">
            <Loader2 className="h-4 w-4 animate-spin" /> Öğrenci röntgeni çekiliyor…
          </p>
        ) : null}
        {analysis && selected === analysis.student.user_id ? (
          <StudentFile analysis={analysis} />
        ) : null}
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        <ShareHuntForm onDone={() => void load()} />
        <TeacherPromoForm
          coupons={coupons}
          onDone={() => void load()}
        />
      </div>
    </div>
  );
}

function StudentChip({
  student,
  active,
  onOpen,
}: {
  student: TeacherStudentCard;
  active: boolean;
  onOpen: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className={cn(
        "rounded-xl border px-3 py-3 text-left transition",
        active
          ? "border-orange-400 bg-orange-500/15"
          : "border-zinc-200 hover:border-orange-300 dark:border-zinc-800",
      )}
    >
      <p className="text-sm font-semibold text-zinc-900 dark:text-white">
        {student.display_name}
      </p>
      <p className="mt-1 text-[11px] text-zinc-500">
        {student.baseline_score.toFixed(1)} net bandı · {student.weak_topics[0] || "konu yok"}
      </p>
    </button>
  );
}

function StudentFile({ analysis }: { analysis: TeacherStudentAnalysis }) {
  return (
    <div className="mt-5 space-y-4 border-t border-zinc-200 pt-5 dark:border-zinc-800">
      <div>
        <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-orange-600">
          Öğrenci takip
        </p>
        <h3 className="text-xl font-semibold text-zinc-900 dark:text-white">
          {analysis.student.display_name}
        </h3>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          {analysis.analysis_summary || "Teşhis özeti henüz yok."}
        </p>
      </div>
      <MistakeDoctorCard report={analysis.doctor} hideCta />
      <div>
        <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-zinc-500">
          Tuzak defteri
        </p>
        <ul className="mt-2 max-h-80 space-y-2 overflow-y-auto">
          {analysis.traps.length === 0 ? (
            <li className="text-sm text-zinc-500">Bu öğrencinin tuzağı yok.</li>
          ) : (
            analysis.traps.map((trap) => (
              <li
                key={trap.id}
                className="rounded-xl border border-zinc-200 p-3 text-sm dark:border-zinc-800"
              >
                <p className="text-[11px] text-orange-600">{trap.topic || "Konu"}</p>
                <p className="mt-1 text-zinc-800 dark:text-zinc-200">{trap.question_text}</p>
                <p className="mt-2 text-xs text-zinc-500">
                  Seçilen {trap.chosen || "?"} · doğru {trap.correct || "?"}
                  {trap.time_trap_triggered ? " · süre tuzağı" : ""}
                </p>
                {trap.teacher_note ? (
                  <p className="mt-2 text-xs text-zinc-600 dark:text-zinc-400">
                    {trap.teacher_note}
                  </p>
                ) : null}
              </li>
            ))
          )}
        </ul>
      </div>
    </div>
  );
}

function ShareHuntForm({ onDone }: { onDone: () => void }) {
  const [title, setTitle] = useState("Sazan Avı");
  const [topic, setTopic] = useState("");
  const [question, setQuestion] = useState("");
  const [options, setOptions] = useState({ A: "", B: "", C: "", D: "", E: "" });
  const [correct, setCorrect] = useState("A");
  const [explanation, setExplanation] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const [error, setError] = useState("");

  async function send() {
    setBusy(true);
    setError("");
    setNote("");
    try {
      const packed = Object.fromEntries(
        Object.entries(options).filter(([, value]) => value.trim()),
      );
      await shareTeacherResource({
        title,
        topic,
        question_text: question,
        options: packed,
        correct,
        explanation,
      });
      setNote("Sınıfa Sazan Avı gönderildi.");
      setQuestion("");
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Paylaşılamadı");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="rounded-2xl border border-zinc-200 bg-white/70 p-5 dark:border-zinc-800 dark:bg-zinc-950/50">
      <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-orange-600">
        Sazan Avı
      </p>
      <h2 className="mt-1 text-lg font-semibold text-zinc-900 dark:text-white">
        Özel soru seti paylaş
      </h2>
      <div className="mt-4 grid gap-2">
        <Input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Başlık" />
        <Input value={topic} onChange={(event) => setTopic(event.target.value)} placeholder="Konu" />
        <textarea
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="Soru metni"
          className="min-h-24 rounded-xl border border-zinc-300 bg-white px-4 py-3 text-sm dark:border-zinc-800 dark:bg-zinc-950/70"
        />
        {(["A", "B", "C", "D", "E"] as const).map((key) => (
          <Input
            key={key}
            value={options[key]}
            onChange={(event) => setOptions((prev) => ({ ...prev, [key]: event.target.value }))}
            placeholder={`${key} şıkkı`}
          />
        ))}
        <select
          value={correct}
          onChange={(event) => setCorrect(event.target.value)}
          className="h-12 rounded-xl border border-zinc-300 bg-white px-3 text-sm dark:border-zinc-800 dark:bg-zinc-950/70"
        >
          {["A", "B", "C", "D", "E"].map((key) => (
            <option key={key} value={key}>
              Doğru şık {key}
            </option>
          ))}
        </select>
        <Input
          value={explanation}
          onChange={(event) => setExplanation(event.target.value)}
          placeholder="Yanlışta gösterilecek açıklama"
        />
      </div>
      {note ? <p className="mt-2 text-sm text-emerald-700">{note}</p> : null}
      {error ? <p className="mt-2 text-sm text-red-500">{error}</p> : null}
      <Button type="button" className="mt-3" disabled={busy} onClick={() => void send()}>
        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
        Sınıfa at
      </Button>
    </section>
  );
}

function TeacherPromoForm({
  coupons,
  onDone,
}: {
  coupons: PromoCoupon[];
  onDone: () => void;
}) {
  const [code, setCode] = useState("");
  const [value, setValue] = useState(20);
  const [maxUses, setMaxUses] = useState(1000);
  const [enroll, setEnroll] = useState(true);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const [error, setError] = useState("");

  async function create() {
    setBusy(true);
    setError("");
    setNote("");
    try {
      const data = await createTeacherPromo({
        code,
        discount_type: "percentage",
        value,
        max_uses: maxUses,
        enroll_to_class: enroll,
      });
      setNote(data.message);
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Kupon üretilemedi");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="rounded-2xl border border-zinc-200 bg-white/70 p-5 dark:border-zinc-800 dark:bg-zinc-950/50">
      <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-orange-600">
        Sınıf kuponu
      </p>
      <h2 className="mt-1 text-lg font-semibold text-zinc-900 dark:text-white">
        Otomatik öğrenci eşleştirme
      </h2>
      <div className="mt-4 grid gap-2">
        <Input
          value={code}
          onChange={(event) => setCode(event.target.value.toUpperCase())}
          placeholder="AYSE20"
          className="font-mono"
        />
        <label className="grid gap-1 text-xs text-zinc-500">
          İndirim oranı (%)
          <Input
            type="number"
            min={1}
            max={100}
            value={value}
            onChange={(event) => setValue(Number(event.target.value))}
          />
        </label>
        <label className="grid gap-1 text-xs text-zinc-500">
          Kullanım limiti
          <Input
            type="number"
            min={0}
            value={maxUses}
            onChange={(event) => setMaxUses(Number(event.target.value))}
          />
        </label>
        <label className="flex items-start gap-2 rounded-xl border border-zinc-200 p-3 text-sm dark:border-zinc-800">
          <input
            type="checkbox"
            checked={enroll}
            onChange={(event) => setEnroll(event.target.checked)}
            className="mt-1"
          />
          <span>Bu kuponu kullananlar doğrudan sınıfıma eklensin</span>
        </label>
      </div>
      {note ? <p className="mt-2 text-sm text-emerald-700">{note}</p> : null}
      {error ? <p className="mt-2 text-sm text-red-500">{error}</p> : null}
      <Button type="button" className="mt-3" disabled={busy} onClick={() => void create()}>
        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Tag className="h-4 w-4" />}
        Kupon üret
      </Button>
      <ul className="mt-4 space-y-2 text-xs text-zinc-500">
        {coupons.map((coupon) => (
          <li key={coupon.id} className="flex justify-between font-mono">
            <span>{coupon.code}</span>
            <span>
              {coupon.used_count}/{coupon.max_uses || "∞"}
              {coupon.enroll_to_class ? " · sınıf" : ""}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
