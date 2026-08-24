"use client";

import { useEffect, useState } from "react";
import { CalendarDays, Link2, Loader2, Plus, Sparkles, Tag, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { TurkishDatePicker } from "@/components/admin/turkish-date-picker";
import {
  createPromo,
  feedOsymArchives,
  getRagStatus,
  grantAdminCredits,
  grantAdminPro,
  adminSetPassword,
  adminUpdateUser,
  listAdminFeedback,
  listAdminUsers,
  listExamSchedules,
  listPromos,
  setAdminFeedbackStatus,
  updateExamSchedule,
  updateExamToday,
  type AdminFeedbackItem,
  type AdminUserRow,
  type ArchiveFeedResult,
  type ExamScheduleItem,
  type PromoCoupon,
  type RagStatus,
} from "@/lib/api";
import { getUserId } from "@/lib/user";

const SECRET_KEY = "tilko_admin_secret";

function formatExpiry(raw: string | null) {
  if (!raw) return "—";
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return raw;
  return d.toLocaleDateString("tr-TR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

async function copyText(label: string, value: string) {
  const text = (value || "").trim();
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
    window.alert(`${label} panoya kopyalandı.`);
  } catch {
    window.prompt("Kopyala:", text);
  }
}

export default function AdminArchivePage() {
  const [secret, setSecret] = useState("");
  const [examTarget, setExamTarget] = useState("kpss_lisans");
  const [year, setYear] = useState(2025);
  const [files, setFiles] = useState<File[]>([]);
  const [urlText, setUrlText] = useState("");
  const [status, setStatus] = useState<RagStatus | null>(null);
  const [result, setResult] = useState<ArchiveFeedResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [creditMsg, setCreditMsg] = useState("");
  const [myUserId, setMyUserId] = useState("");
  const [users, setUsers] = useState<AdminUserRow[]>([]);
  const [userQuery, setUserQuery] = useState("");
  const [proDays, setProDays] = useState(31);
  /** Admin yeni şifre atayınca ekranda göster (eski hash okunamaz). */
  const [tempPasswords, setTempPasswords] = useState<Record<string, string>>({});
  const [feedback, setFeedback] = useState<AdminFeedbackItem[]>([]);
  const [feedbackFilter, setFeedbackFilter] = useState<"" | "pending" | "done" | "archived">(
    "pending",
  );
  const [tab, setTab] = useState<
    "archive" | "promo" | "calendar" | "credits" | "users" | "feedback"
  >("feedback");

  useEffect(() => {
    const stored = window.localStorage.getItem(SECRET_KEY) || "";
    if (stored) setSecret(stored);
    setMyUserId(getUserId());
  }, []);

  async function loadUsers(query = userQuery) {
    setError("");
    try {
      window.localStorage.setItem(SECRET_KEY, secret);
      const data = await listAdminUsers(secret, query);
      setUsers(data.users);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Kullanıcılar alınamadı");
    }
  }

  async function loadFeedback(filter = feedbackFilter) {
    setError("");
    try {
      window.localStorage.setItem(SECRET_KEY, secret);
      const data = await listAdminFeedback(secret, filter);
      setFeedback(data.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Geri bildirimler alınamadı");
    }
  }

  async function loadStatus() {
    setError("");
    try {
      window.localStorage.setItem(SECRET_KEY, secret);
      setStatus(await getRagStatus(secret, examTarget));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Durum alınamadı");
    }
  }

  async function feed(useInbox: boolean) {
    setBusy(true);
    setError("");
    setResult(null);
    try {
      window.localStorage.setItem(SECRET_KEY, secret);
      const urls = useInbox
        ? []
        : urlText
            .split(/[\s,]+/)
            .map((item) => item.trim())
            .filter((item) => item.startsWith("http://") || item.startsWith("https://"));
      const data = await feedOsymArchives(secret, {
        exam_target: examTarget,
        exam_year: year,
        files: useInbox ? [] : files,
        urls,
        scan_inbox: useInbox,
      });
      setResult(data);
      setStatus(await getRagStatus(secret, examTarget));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Arşiv işlenemedi");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <section className="rounded-2xl border border-orange-400/40 bg-white/70 p-4 dark:bg-zinc-950/50">
        <label className="grid gap-1 text-xs font-medium text-zinc-600 dark:text-zinc-400">
          Admin anahtarı
          <Input
            type="password"
            value={secret}
            onChange={(event) => {
              const value = event.target.value;
              setSecret(value);
              window.localStorage.setItem(SECRET_KEY, value);
            }}
            placeholder="Render ADMIN_API_SECRET"
          />
        </label>
        <p className="mt-2 text-[11px] text-zinc-500">
          Canlıda Render → Environment →{" "}
          <span className="font-mono">ADMIN_API_SECRET</span> değerini yapıştır.
          Anahtar kayıtlıysa YouTube analizi kredi düşürmez.
        </p>
      </section>
      <div className="grid grid-cols-2 gap-1 rounded-2xl border border-zinc-200 bg-white/70 p-1 sm:grid-cols-3 lg:grid-cols-6 dark:border-zinc-800 dark:bg-zinc-950/50">
        {(
          [
            ["feedback", "Geri bildirim"],
            ["users", "Kullanıcılar"],
            ["credits", "Krediler"],
            ["calendar", "Sınav takvimi"],
            ["archive", "Arşiv"],
            ["promo", "Kupon"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            onClick={() => {
              setTab(id);
              if (id === "users" && secret.trim()) void loadUsers();
              if (id === "feedback" && secret.trim()) void loadFeedback();
            }}
            className={
              tab === id
                ? "rounded-xl bg-orange-500 px-3 py-2 text-sm font-semibold text-zinc-950"
                : "rounded-xl px-3 py-2 text-sm font-medium text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200"
            }
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "feedback" ? (
        <section className="space-y-4 rounded-2xl border border-orange-400/40 bg-white/70 p-5 dark:bg-zinc-950/50">
          <div>
            <h2 className="text-lg font-semibold text-zinc-900 dark:text-white">
              Geliştirmemize Yardım Et
            </h2>
            <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
              Kullanıcıların gönderdiği öneriler burada listelenir.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {(
              [
                ["pending", "Bekleyen"],
                ["done", "Tamamlanan"],
                ["archived", "Arşiv"],
                ["", "Tümü"],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id || "all"}
                type="button"
                onClick={() => {
                  setFeedbackFilter(id);
                  if (secret.trim()) void loadFeedback(id);
                }}
                className={
                  feedbackFilter === id
                    ? "rounded-full bg-orange-500 px-3 py-1 text-xs font-semibold text-zinc-950"
                    : "rounded-full border border-zinc-200 px-3 py-1 text-xs text-zinc-500 dark:border-zinc-700"
                }
              >
                {label}
              </button>
            ))}
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={!secret.trim() || busy}
              onClick={() => void loadFeedback()}
            >
              Yenile
            </Button>
          </div>
          {error ? <p className="text-sm text-red-400">{error}</p> : null}
          {creditMsg ? (
            <p className="text-sm text-emerald-700 dark:text-emerald-300">{creditMsg}</p>
          ) : null}
          <div className="space-y-3">
            {feedback.length === 0 ? (
              <p className="rounded-xl border border-dashed border-zinc-300 px-4 py-8 text-center text-sm text-zinc-500 dark:border-zinc-700">
                Henüz geri bildirim yok. Anahtarı yazıp Yenile’ye bas.
              </p>
            ) : (
              feedback.map((item) => (
                <article
                  key={item.id}
                  className="rounded-xl border border-zinc-200 bg-white/80 p-4 dark:border-zinc-800 dark:bg-zinc-950/60"
                >
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <p className="font-semibold text-zinc-900 dark:text-white">
                        {item.display_name || item.user_id}
                      </p>
                      <p className="text-[11px] text-zinc-500">
                        {item.email || item.phone || item.user_id} ·{" "}
                        {item.category_label} · {formatExpiry(item.created_at)}
                      </p>
                    </div>
                    <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
                      {item.status}
                    </span>
                  </div>
                  <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-zinc-800 dark:text-zinc-200">
                    {item.message}
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {item.status !== "done" ? (
                      <Button
                        type="button"
                        size="sm"
                        disabled={busy || !secret.trim()}
                        onClick={() => {
                          void (async () => {
                            setBusy(true);
                            setError("");
                            setCreditMsg("");
                            try {
                              const data = await setAdminFeedbackStatus(
                                secret,
                                item.id,
                                "done",
                              );
                              setCreditMsg(data.message);
                              await loadFeedback();
                            } catch (err) {
                              setError(
                                err instanceof Error
                                  ? err.message
                                  : "Güncellenemedi",
                              );
                            } finally {
                              setBusy(false);
                            }
                          })();
                        }}
                      >
                        Tamamlandı
                      </Button>
                    ) : null}
                    {item.status !== "archived" ? (
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        disabled={busy || !secret.trim()}
                        onClick={() => {
                          void (async () => {
                            setBusy(true);
                            setError("");
                            setCreditMsg("");
                            try {
                              const data = await setAdminFeedbackStatus(
                                secret,
                                item.id,
                                "archived",
                              );
                              setCreditMsg(data.message);
                              await loadFeedback();
                            } catch (err) {
                              setError(
                                err instanceof Error
                                  ? err.message
                                  : "Arşivlenemedi",
                              );
                            } finally {
                              setBusy(false);
                            }
                          })();
                        }}
                      >
                        Arşivle
                      </Button>
                    ) : null}
                  </div>
                </article>
              ))
            )}
          </div>
        </section>
      ) : null}

      {tab === "users" ? (
        <section className="space-y-4 rounded-2xl border border-orange-400/40 bg-white/70 p-5 dark:bg-zinc-950/50">
          <div>
            <h2 className="text-lg font-semibold text-zinc-900 dark:text-white">
              Kayıtlı kullanıcılar
            </h2>
            <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
              E-posta ve telefon her satırda görünür (kopyala). Eski şifreler hash
              ile saklanır, okunamaz — yeni şifre atayınca burada kopyalanabilir
              kalır.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Input
              value={userQuery}
              onChange={(event) => setUserQuery(event.target.value)}
              placeholder="Ara: ad, e-posta, telefon…"
              className="min-w-[200px] flex-1"
            />
            <Input
              type="number"
              min={1}
              max={3650}
              value={proDays}
              onChange={(event) => setProDays(Number(event.target.value) || 31)}
              className="w-24"
              title="Pro gün"
            />
            <Button
              type="button"
              variant="outline"
              disabled={!secret.trim() || busy}
              onClick={() => void loadUsers()}
            >
              Yenile
            </Button>
          </div>
          {error ? <p className="text-sm text-red-400">{error}</p> : null}
          {creditMsg ? (
            <p className="text-sm text-emerald-700 dark:text-emerald-300">{creditMsg}</p>
          ) : null}
          <div className="overflow-x-auto rounded-xl border border-zinc-200 dark:border-zinc-800">
            <table className="min-w-full text-left text-xs">
              <thead className="bg-zinc-50 text-[10px] uppercase tracking-wide text-zinc-500 dark:bg-zinc-900">
                <tr>
                  <th className="px-3 py-2">Kişi</th>
                  <th className="px-3 py-2">Giriş bilgileri</th>
                  <th className="px-3 py-2">Sınav</th>
                  <th className="px-3 py-2">Pro</th>
                  <th className="px-3 py-2">İşlem</th>
                </tr>
              </thead>
              <tbody>
                {users.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-3 py-6 text-center text-zinc-500">
                      Liste boş. Anahtarı yazıp Yenile’ye bas.
                    </td>
                  </tr>
                ) : (
                  users.map((row) => {
                    const tempPass = tempPasswords[row.user_id] || "";
                    return (
                    <tr
                      key={row.user_id}
                      className="border-t border-zinc-100 dark:border-zinc-800"
                    >
                      <td className="px-3 py-2 align-top">
                        <p className="font-medium text-zinc-900 dark:text-white">
                          {row.display_name || "İsimsiz hesap"}
                        </p>
                        <p className="font-mono text-[10px] text-zinc-500">
                          {row.user_id}
                        </p>
                        <p className="text-[10px] text-zinc-400">
                          {formatExpiry(row.created_at)} · {row.role}
                          {row.has_google ? " · Google" : ""}
                        </p>
                        {!row.email && !row.phone ? (
                          <p className="mt-1 text-[10px] font-medium text-amber-600">
                            Eksik profil — e-posta/telefon ekle
                          </p>
                        ) : null}
                      </td>
                      <td className="px-3 py-2 align-top text-zinc-700 dark:text-zinc-200">
                        <div className="space-y-1.5">
                          <div className="flex flex-wrap items-center gap-1">
                            <span className="font-medium">
                              {row.email || "e-posta yok"}
                            </span>
                            {row.email ? (
                              <button
                                type="button"
                                className="rounded bg-zinc-100 px-1.5 py-0.5 text-[10px] font-semibold text-zinc-700 hover:bg-orange-100 dark:bg-zinc-800 dark:text-zinc-200"
                                onClick={() => void copyText("E-posta", row.email)}
                              >
                                Kopyala
                              </button>
                            ) : null}
                          </div>
                          <div className="flex flex-wrap items-center gap-1">
                            <span>{row.phone || "telefon yok"}</span>
                            {row.phone ? (
                              <button
                                type="button"
                                className="rounded bg-zinc-100 px-1.5 py-0.5 text-[10px] font-semibold text-zinc-700 hover:bg-orange-100 dark:bg-zinc-800 dark:text-zinc-200"
                                onClick={() => void copyText("Telefon", row.phone)}
                              >
                                Kopyala
                              </button>
                            ) : null}
                          </div>
                          <div className="rounded-lg border border-zinc-200 bg-zinc-50 px-2 py-1.5 dark:border-zinc-700 dark:bg-zinc-900/60">
                            <p className="text-[10px] uppercase tracking-wide text-zinc-500">
                              Şifre
                            </p>
                            {tempPass ? (
                              <div className="mt-0.5 flex flex-wrap items-center gap-1">
                                <code className="font-mono text-sm font-semibold text-emerald-700 dark:text-emerald-300">
                                  {tempPass}
                                </code>
                                <button
                                  type="button"
                                  className="rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-800"
                                  onClick={() => void copyText("Şifre", tempPass)}
                                >
                                  Kopyala
                                </button>
                              </div>
                            ) : (
                              <p className="mt-0.5 text-[11px] text-zinc-600 dark:text-zinc-400">
                                {row.has_password
                                  ? "Kayıtlı (hash) — eski şifre okunamaz. Yeni şifre ata."
                                  : "Şifre yok — aşağıdan ata."}
                              </p>
                            )}
                          </div>
                        </div>
                      </td>
                      <td className="px-3 py-2 align-top">{row.exam_target || "—"}</td>
                      <td className="px-3 py-2 align-top">
                        <p
                          className={
                            row.is_premium
                              ? "font-semibold text-emerald-600"
                              : "text-zinc-500"
                          }
                        >
                          {row.is_premium ? "Pro var" : "Yok"}
                        </p>
                        <p className="text-[10px] text-zinc-500">
                          {row.subscription_status || "—"}
                        </p>
                        <p className="text-[10px] text-zinc-500">
                          Bitiş: {formatExpiry(row.subscription_expires_at)}
                        </p>
                        <p className="text-[10px] text-zinc-400">
                          Kredi: {row.ai_credits_left}
                        </p>
                      </td>
                      <td className="px-3 py-2 align-top">
                        <div className="flex flex-col gap-1">
                          <Button
                            type="button"
                            size="sm"
                            disabled={busy || !secret.trim()}
                            onClick={() => {
                              void (async () => {
                                setBusy(true);
                                setError("");
                                setCreditMsg("");
                                try {
                                  const data = await grantAdminPro(secret, {
                                    user_id: row.user_id,
                                    days: proDays,
                                  });
                                  setCreditMsg(data.message);
                                  await loadUsers();
                                } catch (err) {
                                  setError(
                                    err instanceof Error
                                      ? err.message
                                      : "Pro verilemedi",
                                  );
                                } finally {
                                  setBusy(false);
                                }
                              })();
                            }}
                          >
                            Pro ver
                          </Button>
                          <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            disabled={busy || !secret.trim()}
                            onClick={() => {
                              void (async () => {
                                setBusy(true);
                                setError("");
                                setCreditMsg("");
                                try {
                                  const data = await grantAdminPro(secret, {
                                    user_id: row.user_id,
                                    revoke: true,
                                  });
                                  setCreditMsg(data.message);
                                  await loadUsers();
                                } catch (err) {
                                  setError(
                                    err instanceof Error
                                      ? err.message
                                      : "Pro kaldırılamadı",
                                  );
                                } finally {
                                  setBusy(false);
                                }
                              })();
                            }}
                          >
                            Pro kaldır
                          </Button>
                          <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            disabled={busy || !secret.trim()}
                            onClick={() => {
                              void (async () => {
                                const name = window.prompt(
                                  "Ad soyad:",
                                  row.display_name || "",
                                );
                                if (name == null) return;
                                const mail = window.prompt(
                                  "E-posta (giriş için):",
                                  row.email || "",
                                );
                                if (mail == null) return;
                                const pass = window.prompt(
                                  "Yeni şifre (min 8, boş = değiştirme):",
                                  "",
                                );
                                if (pass == null) return;
                                if (pass.trim() && pass.trim().length < 8) {
                                  setError("Şifre en az 8 karakter olmalı.");
                                  return;
                                }
                                setBusy(true);
                                setError("");
                                setCreditMsg("");
                                try {
                                  const data = await adminUpdateUser(secret, {
                                    user_id: row.user_id,
                                    display_name: name.trim(),
                                    email: mail.trim(),
                                    new_password: pass.trim() || null,
                                  });
                                  if (pass.trim()) {
                                    setTempPasswords((prev) => ({
                                      ...prev,
                                      [row.user_id]: pass.trim(),
                                    }));
                                  }
                                  setCreditMsg(
                                    `${data.message} Giriş: ${data.email || row.user_id}${
                                      pass.trim() ? ` · şifre: ${pass.trim()}` : ""
                                    }`,
                                  );
                                  await loadUsers();
                                } catch (err) {
                                  setError(
                                    err instanceof Error
                                      ? err.message
                                      : "Güncellenemedi",
                                  );
                                } finally {
                                  setBusy(false);
                                }
                              })();
                            }}
                          >
                            Hesabı onar
                          </Button>
                          <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            disabled={busy || !secret.trim()}
                            onClick={() => {
                              void (async () => {
                                const next = window.prompt(
                                  `${row.display_name || row.email || row.user_id} için yeni şifre (min 8):`,
                                );
                                if (!next || next.trim().length < 8) {
                                  if (next != null) {
                                    setError("Şifre en az 8 karakter olmalı.");
                                  }
                                  return;
                                }
                                const plain = next.trim();
                                setBusy(true);
                                setError("");
                                setCreditMsg("");
                                try {
                                  const data = await adminSetPassword(secret, {
                                    user_id: row.user_id,
                                    new_password: plain,
                                  });
                                  setTempPasswords((prev) => ({
                                    ...prev,
                                    [row.user_id]: plain,
                                  }));
                                  setCreditMsg(
                                    `${data.message} Şifre: ${plain} (satırda da görünür)`,
                                  );
                                  await loadUsers();
                                } catch (err) {
                                  setError(
                                    err instanceof Error
                                      ? err.message
                                      : "Şifre güncellenemedi",
                                  );
                                } finally {
                                  setBusy(false);
                                }
                              })();
                            }}
                          >
                            Şifre ata / göster
                          </Button>
                        </div>
                      </td>
                    </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      {tab === "credits" ? (
        <section className="rounded-2xl border border-orange-400/40 bg-white/70 p-5 dark:bg-zinc-950/50">
          <h2 className="text-lg font-semibold text-zinc-900 dark:text-white">
            Test kredisi
          </h2>
          <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
            Bu tarayıcıdaki hesabın kredisini doldur veya Pro (sınırsız) aç.
            Admin anahtarı kayıtlıyken Analiz et zaten kredi yakmaz.
          </p>
          <p className="mt-2 font-mono text-[11px] text-zinc-500">
            user: {myUserId || "…"}
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            <Button
              type="button"
              disabled={busy || !secret.trim()}
              onClick={() => {
                void (async () => {
                  setBusy(true);
                  setError("");
                  setCreditMsg("");
                  try {
                    const data = await grantAdminCredits(secret, {
                      user_id: getUserId(),
                      credits: 7,
                      premium: false,
                    });
                    setCreditMsg(data.message);
                  } catch (err) {
                    setError(
                      err instanceof Error ? err.message : "Kredi doldurulamadı",
                    );
                  } finally {
                    setBusy(false);
                  }
                })();
              }}
            >
              Krediyi 7 yap
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={busy || !secret.trim()}
              onClick={() => {
                void (async () => {
                  setBusy(true);
                  setError("");
                  setCreditMsg("");
                  try {
                    const data = await grantAdminCredits(secret, {
                      user_id: getUserId(),
                      premium: true,
                    });
                    setCreditMsg(data.message);
                  } catch (err) {
                    setError(
                      err instanceof Error ? err.message : "Pro açılamadı",
                    );
                  } finally {
                    setBusy(false);
                  }
                })();
              }}
            >
              Sınırsız test (Pro)
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={busy || !secret.trim()}
              onClick={() => {
                void (async () => {
                  setBusy(true);
                  setError("");
                  setCreditMsg("");
                  try {
                    const data = await grantAdminCredits(secret, {
                      user_id: getUserId(),
                      premium: false,
                      credits: 7,
                    });
                    setCreditMsg(`Pro kapandı. ${data.message}`);
                  } catch (err) {
                    setError(
                      err instanceof Error ? err.message : "Pro kapatılamadı",
                    );
                  } finally {
                    setBusy(false);
                  }
                })();
              }}
            >
              Pro’yu kapat
            </Button>
          </div>
          {creditMsg ? (
            <p className="mt-3 text-sm text-emerald-700 dark:text-emerald-300">
              {creditMsg}
            </p>
          ) : null}
          {error ? <p className="mt-3 text-sm text-red-400">{error}</p> : null}
        </section>
      ) : null}

      {tab === "archive" ? (
      <>
      <section className="glow-orange rounded-2xl border-2 border-orange-400/70 bg-white/60 p-6 backdrop-blur-xl dark:bg-zinc-950/50">
        <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-orange-600 dark:text-orange-300">
          RAG motoru
        </p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-zinc-900 dark:text-white">
          ÖSYM arşiv besleme
        </h1>
        <p className="mt-3 text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">
          PDF dosyası yükle veya doğrudan PDF linkini yapıştır. Model kalıpları çıkarır,{" "}
          <span className="font-mono text-xs">osym_style_guide</span> ve soru
          havuzu sinyallerini günceller. Inbox:{" "}
          <span className="font-mono text-xs">backend/osym_archive_docs/inbox</span>
        </p>
        <div className="mt-4 grid gap-3">
          <Input
            value={examTarget}
            onChange={(event) => setExamTarget(event.target.value)}
            placeholder="kpss_lisans / yks / lgs"
          />
          <Input
            type="number"
            min={2016}
            max={2030}
            value={year}
            onChange={(event) => setYear(Number(event.target.value))}
          />
          <label className="grid gap-1 text-xs font-medium text-zinc-600 dark:text-zinc-400">
            <span className="inline-flex items-center gap-1">
              <Link2 className="h-3.5 w-3.5" />
              PDF linkleri
            </span>
            <textarea
              value={urlText}
              onChange={(event) => setUrlText(event.target.value)}
              rows={3}
              placeholder="https://dokuman.osym.gov.tr/.../soru.pdf"
              className="min-h-[4.5rem] w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 outline-none ring-orange-400/40 placeholder:text-zinc-400 focus:ring-2 dark:border-zinc-700 dark:bg-zinc-950 dark:text-white"
            />
          </label>
          <p className="text-[11px] text-zinc-500">
            Her satıra bir link. Dosya ve link aynı anda da gönderilebilir.
          </p>
          <input
            type="file"
            accept=".pdf,.txt,.md,.json"
            multiple
            className="text-sm text-zinc-500 file:mr-3 file:rounded-full file:border-0 file:bg-orange-500/15 file:px-3 file:py-1 file:text-orange-700"
            onChange={(event) => setFiles(Array.from(event.target.files || []))}
          />
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <Button type="button" variant="outline" onClick={() => void loadStatus()}>
            Durumu çek
          </Button>
          <Button type="button" disabled={busy} onClick={() => void feed(false)}>
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
            PDF işle
          </Button>
          <Button type="button" variant="outline" disabled={busy} onClick={() => void feed(true)}>
            Inbox tara
          </Button>
        </div>
        {error ? <p className="mt-3 text-sm text-red-500">{error}</p> : null}
      </section>

      {status ? (
        <section className="rounded-2xl border border-orange-400/40 bg-white/55 p-5 text-sm backdrop-blur-xl dark:bg-zinc-950/45">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-orange-600">
            Havuz
          </p>
          <p className="mt-2 text-zinc-700 dark:text-zinc-300">
            {status.docs} belge · {status.chunks} parça · {status.highlights} hoca
            vurgusu · stil rev {status.style.revision}
          </p>
          {status.topic_signals.length ? (
            <ul className="mt-3 space-y-1 text-xs text-zinc-500">
              {status.topic_signals.map((item) => (
                <li key={item.topic}>
                  {item.topic} · {item.weight} · {item.source}
                </li>
              ))}
            </ul>
          ) : null}
        </section>
      ) : null}

      {result ? (
        <section className="rounded-2xl border border-orange-400/40 bg-white/55 p-5 text-sm backdrop-blur-xl dark:bg-zinc-950/45">
          <p className="text-zinc-700 dark:text-zinc-300">
            {result.processed} kayıt işlendi. Stil revizyon: {result.style_revision}.
          </p>
          {result.results.length ? (
            <ul className="mt-3 space-y-1 text-xs text-zinc-500">
              {result.results.map((item, index) => {
                const name = String(item.filename || item.source_url || `kayıt ${index + 1}`);
                if (item.error) {
                  return (
                    <li key={`${name}-${index}`} className="text-red-500">
                      {name} · {String(item.error)}
                    </li>
                  );
                }
                return (
                  <li key={`${name}-${index}`}>
                    {name}
                    {item.skipped ? " · zaten vardı" : ` · ${item.chunks ?? 0} parça`}
                  </li>
                );
              })}
            </ul>
          ) : null}
        </section>
      ) : null}
      </> ) : null}

      {tab === "promo" ? (
        <PromoAdmin secret={secret} onSecret={(value) => setSecret(value)} />
      ) : null}

      {tab === "calendar" ? (
        <ExamCalendarAdmin secret={secret} onSecret={(value) => setSecret(value)} />
      ) : null}
    </div>
  );
}

function ExamCalendarAdmin({
  secret,
  onSecret,
}: {
  secret: string;
  onSecret: (value: string) => void;
}) {
  const [exams, setExams] = useState<ExamScheduleItem[]>([]);
  const [today, setToday] = useState("");
  const [todayLabel, setTodayLabel] = useState("");
  const [todayOverride, setTodayOverride] = useState(false);
  const [realToday, setRealToday] = useState("");
  const [realTodayLabel, setRealTodayLabel] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [note, setNote] = useState("");

  async function persistSecret() {
    window.localStorage.setItem(SECRET_KEY, secret);
    onSecret(secret);
  }

  function applyList(data: {
    exams: ExamScheduleItem[];
    today?: string;
    today_label?: string;
    today_override?: boolean;
    real_today?: string;
    real_today_label?: string;
    message?: string;
  }) {
    setExams(data.exams);
    setToday((data.today || "").slice(0, 10));
    setTodayLabel(data.today_label || "");
    setTodayOverride(Boolean(data.today_override));
    setRealToday((data.real_today || "").slice(0, 10));
    setRealTodayLabel(data.real_today_label || "");
    if (data.message) setNote(data.message);
  }

  async function load() {
    setError("");
    if (!secret.trim()) {
      setError("Admin anahtarını üstteki alana yaz (yerelde tilko-admin-dev).");
      return;
    }
    try {
      await persistSecret();
      applyList(await listExamSchedules(secret));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Takvim alınamadı");
    }
  }

  useEffect(() => {
    if (!secret) return;
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [secret]);

  async function save(examTarget: string, examDate: string) {
    setBusy(examTarget);
    setError("");
    setNote("");
    try {
      await persistSecret();
      const row = await updateExamSchedule(secret, {
        exam_target: examTarget,
        exam_date: examDate,
      });
      setExams((prev) =>
        prev.map((item) => (item.exam_target === examTarget ? { ...item, ...row } : item)),
      );
      setNote(row.message || `${row.label} güncellendi. Kalan ${row.days_remaining} gün.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Tarih kaydedilemedi");
    } finally {
      setBusy("");
    }
  }

  async function saveToday(next: string, reset = false) {
    setBusy("today");
    setError("");
    setNote("");
    try {
      await persistSecret();
      applyList(
        await updateExamToday(secret, reset ? { reset: true } : { exam_date: next }),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Bugün kaydedilemedi");
    } finally {
      setBusy("");
    }
  }

  return (
    <section className="glow-orange rounded-2xl border-2 border-orange-400/70 bg-white/60 p-6 backdrop-blur-xl dark:bg-zinc-950/50">
      <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-orange-600 dark:text-orange-300">
        Sınav takvimini düzenle
      </p>
      <h2 className="mt-2 text-2xl font-semibold tracking-tight text-zinc-900 dark:text-white">
        Resmi sınav günleri
      </h2>
      <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
        Üstteki Bugün alanı hesap günüdür. Alttaki sınav tarihleri Türkçe yazılır. Kalan
        gün, bu iki tarih arasındaki farktır.
      </p>
      <div className="mt-4">
        <Button type="button" variant="outline" onClick={() => void load()}>
          <CalendarDays className="h-4 w-4" />
          Listeyi yenile
        </Button>
      </div>
      {note ? <p className="mt-3 text-sm text-emerald-700 dark:text-emerald-300">{note}</p> : null}
      {error ? <p className="mt-3 text-sm text-red-500">{error}</p> : null}

      <div className="mt-5 rounded-xl border-2 border-orange-300/80 bg-orange-50/80 p-4 dark:border-orange-500/40 dark:bg-orange-950/30">
        <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-orange-700 dark:text-orange-300">
          Bugün
        </p>
        <p className="mt-1 text-xl font-semibold text-zinc-900 dark:text-white">
          {todayLabel || "Tarih yüklenmedi"}
        </p>
        <p className="mt-1 text-xs text-zinc-600 dark:text-zinc-400">
          {todayOverride
            ? "Bu tarih elle ayarlandı. Ana sayfadaki kalan gün de buna göre."
            : "Gerçek İstanbul günü. Değiştirirsen sayaç bu yeni güne göre hesaplanır."}
        </p>
        {today ? (
          <div className="mt-3">
            <TurkishDatePicker
              value={today}
              disabled={Boolean(busy)}
              onChange={(next) => {
                setToday(next);
                void saveToday(next);
              }}
            />
          </div>
        ) : null}
        {todayOverride ? (
          <Button
            type="button"
            variant="outline"
            className="mt-3"
            disabled={Boolean(busy)}
            onClick={() => void saveToday(realToday, true)}
          >
            Gerçek bugüne dön{realTodayLabel ? ` · ${realTodayLabel}` : ""}
          </Button>
        ) : null}
      </div>

      <div className="mt-5 space-y-3">
        {exams.length === 0 ? (
          <p className="text-sm text-zinc-500">Takvim yüklenmedi. Admin anahtarını yazıp yenile.</p>
        ) : (
          exams.map((exam) => (
            <div
              key={exam.exam_target}
              className="grid gap-2 rounded-xl border border-zinc-200 bg-white/70 p-4 dark:border-zinc-800 dark:bg-zinc-950/40"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold text-zinc-900 dark:text-white">
                    {exam.label}
                  </p>
                  <p className="mt-1 text-base font-medium text-zinc-800 dark:text-zinc-100">
                    {exam.exam_date_label || exam.exam_date}
                  </p>
                  <p className="text-[11px] text-zinc-500">
                    {exam.days_remaining >= 0
                      ? `${exam.days_remaining} gün kaldı`
                      : `${Math.abs(exam.days_remaining)} gün önceydi`}
                  </p>
                </div>
                {busy === exam.exam_target ? (
                  <Loader2 className="h-4 w-4 animate-spin text-orange-500" />
                ) : null}
              </div>
              <TurkishDatePicker
                value={exam.exam_date.slice(0, 10)}
                disabled={Boolean(busy)}
                onChange={(next) => {
                  setExams((prev) =>
                    prev.map((item) =>
                      item.exam_target === exam.exam_target
                        ? { ...item, exam_date: next }
                        : item,
                    ),
                  );
                  void save(exam.exam_target, next);
                }}
              />
            </div>
          ))
        )}
      </div>
    </section>
  );
}

function usageLabel(status: string) {
  if (status === "active") return "aktif";
  if (status === "expired") return "süresi doldu";
  return "limit doldu";
}

function UsageBar({ used, max }: { used: number; max: number }) {
  if (max <= 0) {
    return (
      <p className="mt-3 text-xs font-medium text-zinc-600 dark:text-zinc-300">
        {used} / sınırsız Kullanıldı
      </p>
    );
  }
  const pct = Math.min(100, Math.round((used / Math.max(max, 1)) * 100));
  return (
    <div className="mt-3">
      <div className="mb-1.5 flex items-center justify-between text-xs font-medium text-zinc-700 dark:text-zinc-300">
        <span>
          {used} / {max} Kullanıldı
        </span>
        <span className="tabular-nums text-zinc-500">{pct}%</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800">
        <div
          className={`h-full rounded-full transition-all ${
            pct >= 100 ? "bg-red-500" : "bg-orange-500"
          }`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

function PromoAdmin({
  secret,
  onSecret,
}: {
  secret: string;
  onSecret: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [code, setCode] = useState("TILKO20");
  const [kind, setKind] = useState("fixed");
  const [value, setValue] = useState(20);
  const [maxUses, setMaxUses] = useState(1000);
  const [quantity, setQuantity] = useState(1);
  const [expires, setExpires] = useState("");
  const [teacherId, setTeacherId] = useState("");
  const [enroll, setEnroll] = useState(false);
  const [coupons, setCoupons] = useState<PromoCoupon[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");

  async function persistSecret() {
    window.localStorage.setItem(SECRET_KEY, secret);
    onSecret(secret);
  }

  async function loadCoupons() {
    setError("");
    try {
      await persistSecret();
      const data = await listPromos(secret);
      setCoupons(data.coupons);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Kuponlar alınamadı");
    }
  }

  async function create() {
    setBusy(true);
    setError("");
    setNote("");
    try {
      await persistSecret();
      const row = await createPromo(secret, {
        code,
        discount_type: kind,
        value,
        max_uses: maxUses,
        quantity,
        expires_at: expires ? new Date(expires).toISOString() : undefined,
        created_by_teacher_id: teacherId.trim(),
        enroll_to_class: enroll,
      });
      setNote(row.message || `${row.count} kupon oluşturuldu.`);
      setOpen(false);
      const data = await listPromos(secret);
      setCoupons(data.coupons);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Kupon oluşturulamadı");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="glow-orange rounded-2xl border-2 border-orange-400/70 bg-white/60 p-6 backdrop-blur-xl dark:bg-zinc-950/50">
      <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-orange-600 dark:text-orange-300">
        Kupon motoru
      </p>
      <h2 className="mt-2 text-2xl font-semibold tracking-tight text-zinc-900 dark:text-white">
        Toplu üretim ve kullanım limiti
      </h2>
      <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
        Kullanım limiti 1000 ise kod 1000 kişiye kadar geçerlidir. 0 sınırsızdır.
        Toplu üretim aynı indirimle birden fazla benzersiz kod basar.
      </p>
      <div className="mt-4 flex flex-wrap gap-2">
        <Button type="button" onClick={() => setOpen(true)}>
          <Plus className="h-4 w-4" />
          Kupon oluştur
        </Button>
        <Button type="button" variant="outline" onClick={() => void loadCoupons()}>
          Listeyi çek
        </Button>
      </div>
      {note ? <p className="mt-3 text-sm text-emerald-700 dark:text-emerald-300">{note}</p> : null}
      {error && !open ? <p className="mt-3 text-sm text-red-500">{error}</p> : null}

      <div className="mt-5 space-y-3">
        {coupons.length === 0 ? (
          <p className="text-sm text-zinc-500">Henüz kupon yok. Listeyi çek veya oluştur.</p>
        ) : (
          coupons.map((coupon) => (
            <article
              key={coupon.id}
              className="rounded-xl border border-zinc-200 bg-white/70 p-4 text-sm dark:border-zinc-800 dark:bg-zinc-950/40"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="font-mono text-base font-semibold text-zinc-900 dark:text-white">
                    {coupon.code}
                  </p>
                  <p className="mt-1 text-xs text-zinc-500">
                    {coupon.discount_type === "percentage"
                      ? `%${coupon.value}`
                      : `${coupon.value} TL`}
                    {coupon.expires_at
                      ? ` · bitiş ${new Date(coupon.expires_at).toLocaleString("tr-TR")}`
                      : ""}
                  </p>
                </div>
                <span
                  className={
                    coupon.status === "active"
                      ? "text-xs text-emerald-600"
                      : "text-xs text-red-500"
                  }
                >
                  {usageLabel(coupon.status)}
                </span>
              </div>
              <UsageBar used={coupon.used_count} max={coupon.max_uses} />
              {(coupon.used_by?.length ? coupon.used_by : coupon.redemptions).length ? (
                <ul className="mt-3 space-y-1 text-xs text-zinc-600 dark:text-zinc-400">
                  {coupon.redemptions.length
                    ? coupon.redemptions.map((item) => (
                        <li key={`${item.user_id}-${item.used_at}`}>
                          {item.user_id} · {item.payable_amount} TL ödendi (
                          {item.discount_amount} TL indirim)
                          {item.used_at
                            ? ` · ${new Date(item.used_at).toLocaleString("tr-TR")}`
                            : ""}
                        </li>
                      ))
                    : (coupon.used_by || []).map((uid) => <li key={uid}>{uid}</li>)}
                </ul>
              ) : (
                <p className="mt-2 text-xs text-zinc-500">Henüz kullanan yok.</p>
              )}
            </article>
          ))
        )}
      </div>

      {open ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-2xl border border-orange-400/50 bg-white p-5 shadow-2xl dark:bg-zinc-950">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-orange-600">
                  Yeni kupon
                </p>
                <h3 className="mt-1 text-lg font-semibold text-zinc-900 dark:text-white">
                  Toplu üretim
                </h3>
              </div>
              <button
                type="button"
                className="rounded-full p-1 text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-800"
                onClick={() => setOpen(false)}
                aria-label="Kapat"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="mt-4 grid gap-3">
              <label className="grid gap-1 text-xs font-medium text-zinc-600 dark:text-zinc-400">
                Kod
                <Input
                  value={code}
                  onChange={(event) => setCode(event.target.value.toUpperCase())}
                  placeholder="TILKO20"
                  className="font-mono"
                />
              </label>
              <div className="grid grid-cols-2 gap-2">
                <label className="grid gap-1 text-xs font-medium text-zinc-600 dark:text-zinc-400">
                  Tür
                  <select
                    value={kind}
                    onChange={(event) => setKind(event.target.value)}
                    className="h-12 rounded-xl border border-zinc-300 bg-white px-3 text-sm dark:border-zinc-800 dark:bg-zinc-950/70"
                  >
                    <option value="fixed">Sabit TL</option>
                    <option value="percentage">Yüzde</option>
                  </select>
                </label>
                <label className="grid gap-1 text-xs font-medium text-zinc-600 dark:text-zinc-400">
                  Değer
                  <Input
                    type="number"
                    min={1}
                    value={value}
                    onChange={(event) => setValue(Number(event.target.value))}
                  />
                </label>
              </div>
              <label className="grid gap-1 text-xs font-medium text-zinc-600 dark:text-zinc-400">
                Kullanım limiti
                <Input
                  type="number"
                  min={0}
                  value={maxUses}
                  onChange={(event) => setMaxUses(Number(event.target.value))}
                  placeholder="1000"
                />
                <span className="font-normal text-[11px] text-zinc-500">
                  1000 yazarsan kod 1000 kişiye kadar sınırlıdır. 0 = sınırsız.
                </span>
              </label>
              <label className="grid gap-1 text-xs font-medium text-zinc-600 dark:text-zinc-400">
                Toplu üretim adedi
                <Input
                  type="number"
                  min={1}
                  max={500}
                  value={quantity}
                  onChange={(event) => setQuantity(Number(event.target.value))}
                />
                <span className="font-normal text-[11px] text-zinc-500">
                  1 tek kod. 50 yazarsan TILKO20-001 … 050 üretilir.
                </span>
              </label>
              <label className="grid gap-1 text-xs font-medium text-zinc-600 dark:text-zinc-400">
                Son kullanma
                <Input
                  type="datetime-local"
                  value={expires}
                  onChange={(event) => setExpires(event.target.value)}
                />
              </label>
              <label className="grid gap-1 text-xs font-medium text-zinc-600 dark:text-zinc-400">
                Hoca kullanıcı adı (isteğe bağlı)
                <Input
                  value={teacherId}
                  onChange={(event) => setTeacherId(event.target.value)}
                  placeholder="hoca_ayse"
                />
              </label>
              <label className="flex items-start gap-2 text-xs text-zinc-600 dark:text-zinc-400">
                <input
                  type="checkbox"
                  checked={enroll}
                  onChange={(event) => setEnroll(event.target.checked)}
                  className="mt-0.5"
                />
                Bu kuponu kullananlar doğrudan hocanın sınıfına eklensin
              </label>
            </div>
            {error ? <p className="mt-3 text-sm text-red-500">{error}</p> : null}
            <div className="mt-4 flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={() => setOpen(false)}>
                Vazgeç
              </Button>
              <Button type="button" disabled={busy} onClick={() => void create()}>
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Tag className="h-4 w-4" />}
                Üret
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
