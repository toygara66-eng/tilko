"use client";

import { useMemo, useState } from "react";
import { Loader2, GraduationCap, School, Mail, Phone, Globe } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { TilkoLogo } from "@/components/brand/tilko-logo";
import { GoogleSignInButton } from "@/components/auth/google-sign-in";
import { loginAccount, loginWithGoogle, registerAccount, forgotPassword, resetPassword } from "@/lib/api";
import { setAuthMode, setAuthSecret, setStoredRole, setToken } from "@/lib/auth";
import { getUserId, setUserId } from "@/lib/user";
import { EXAM_OPTIONS, type ExamTargetId } from "@/lib/exams";
import { cn } from "@/lib/utils";

type Mode = "student" | "teacher";
type Screen = "login" | "register" | "forgot" | "reset";
type Channel = "google" | "email" | "phone";

const EXAM_FLAT: { id: ExamTargetId; label: string }[] = EXAM_OPTIONS.flatMap((group) =>
  group.children.map((child) => ({
    id: child.id as ExamTargetId,
    label: `${group.title} — ${child.label}`,
  })),
);

export default function GirisPage() {
  const [mode, setMode] = useState<Mode>("student");
  const [screen, setScreen] = useState<Screen>("login");
  const [channel, setChannel] = useState<Channel>("email");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [userId, setUid] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [examTarget, setExamTarget] = useState<ExamTargetId | "">("kpss_lisans");
  const [resetCode, setResetCode] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [info, setInfo] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const isRegister = screen === "register";
  const isForgot = screen === "forgot";
  const isReset = screen === "reset";

  const canSubmit = useMemo(() => {
    if (isForgot) {
      if (channel === "phone") return phone.replace(/\D/g, "").length >= 10;
      return email.trim().includes("@");
    }
    if (isReset) {
      const idOk =
        channel === "phone"
          ? phone.replace(/\D/g, "").length >= 10
          : email.trim().includes("@");
      return idOk && resetCode.trim().length >= 4 && newPassword.length >= 8;
    }
    if (password.length < 8) return false;
    if (mode === "teacher") {
      return userId.trim().length >= 3 && (!isRegister || displayName.trim().length >= 2);
    }
    if (isRegister) {
      if (displayName.trim().length < 2 || !examTarget) return false;
      if (channel === "email") return email.trim().includes("@");
      if (channel === "phone") return phone.replace(/\D/g, "").length >= 10;
      return true;
    }
    if (channel === "email") return email.trim().includes("@") || userId.trim().length >= 3;
    if (channel === "phone") return phone.replace(/\D/g, "").length >= 10;
    return true;
  }, [
    password,
    mode,
    userId,
    isRegister,
    isForgot,
    isReset,
    displayName,
    examTarget,
    channel,
    email,
    phone,
    resetCode,
    newPassword,
  ]);

  function finishSession(
    data: {
      access_token: string;
      role: string;
      user_id: string;
      dashboard?: string;
    },
    passwordForStore?: string,
  ) {
    setToken(data.access_token);
    if (passwordForStore) setAuthSecret(passwordForStore);
    else setAuthMode("google");
    setStoredRole(data.role);
    setUserId(data.user_id);
    window.location.assign(data.dashboard || (data.role === "teacher" ? "/hoca" : "/"));
  }

  async function submit() {
    setBusy(true);
    setError("");
    setInfo("");
    try {
      if (isForgot) {
        const data = await forgotPassword({
          email: channel === "phone" ? "" : email.trim(),
          phone: channel === "phone" ? phone.trim() : "",
        });
        setInfo(
          data.debug_code
            ? `${data.message} Kod: ${data.debug_code}`
            : data.message,
        );
        setScreen("reset");
        return;
      }
      if (isReset) {
        const data = await resetPassword({
          email: channel === "phone" ? "" : email.trim(),
          phone: channel === "phone" ? phone.trim() : "",
          code: resetCode.trim(),
          new_password: newPassword,
        });
        setInfo(data.message);
        setPassword(newPassword);
        setScreen("login");
        setResetCode("");
        setNewPassword("");
        return;
      }
      if (mode === "teacher") {
        const payload = {
          user_id: userId.trim(),
          password,
          role: "teacher" as const,
          display_name: displayName.trim(),
        };
        const data = isRegister
          ? await registerAccount(payload)
          : await loginAccount(payload);
        finishSession(data, password);
        return;
      }

      const payload = {
        password,
        role: "student" as const,
        display_name: displayName.trim(),
        exam_target: isRegister ? examTarget : "",
        email: channel === "email" ? email.trim() : "",
        phone: channel === "phone" ? phone.trim() : "",
        user_id:
          channel === "email" && !isRegister && !email.trim().includes("@")
            ? userId.trim()
            : "",
      };
      const data = isRegister
        ? await registerAccount(payload)
        : await loginAccount(payload);
      finishSession(data, password);
    } catch (err) {
      setError(err instanceof Error ? err.message : "İşlem başarısız");
    } finally {
      setBusy(false);
    }
  }

  async function onGoogle(idToken: string) {
    if (busy || mode !== "student") return;
    if (isRegister && (!displayName.trim() || !examTarget)) {
      setError("Google ile kayıt için ad soyad ve sınav hedefi doldur.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const guest = getUserId();
      const data = await loginWithGoogle({
        id_token: idToken,
        role: "student",
        display_name: displayName.trim(),
        exam_target: isRegister ? examTarget : "",
        link_user_id: guest.startsWith("aday-") ? guest : "",
      });
      finishSession(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Google girişi başarısız");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto flex min-h-[80vh] w-full max-w-md flex-col justify-center px-4 py-8">
      <div className="mb-6 flex items-center gap-3">
        <TilkoLogo size={40} />
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-orange-600">
            TİLKO
          </p>
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-900 dark:text-white">
            {isForgot
              ? "Şifremi unuttum"
              : isReset
                ? "Yeni şifre"
                : isRegister
                  ? "Kayıt ol"
                  : "Giriş"}
          </h1>
        </div>
      </div>

      {!isForgot && !isReset ? (
      <div className="grid grid-cols-2 gap-2 rounded-2xl border border-zinc-200 bg-white/70 p-1 dark:border-zinc-800 dark:bg-zinc-950/50">
        {(
          [
            ["student", "Öğrenci", GraduationCap],
            ["teacher", "Hoca", School],
          ] as const
        ).map(([id, label, Icon]) => (
          <button
            key={id}
            type="button"
            onClick={() => setMode(id)}
            className={cn(
              "flex items-center justify-center gap-2 rounded-xl px-3 py-3 text-sm font-semibold transition",
              mode === id
                ? "bg-orange-500 text-zinc-950 shadow-[0_0_16px_rgba(251,146,60,0.35)]"
                : "text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200",
            )}
          >
            <Icon className="h-4 w-4" />
            {label}
          </button>
        ))}
      </div>
      ) : null}

      {!isForgot && !isReset ? (
      <div className="mt-3 grid grid-cols-2 gap-2 rounded-2xl border border-zinc-200 bg-white/50 p-1 dark:border-zinc-800">
        {(
          [
            ["login", "Giriş yap"],
            ["register", "Kayıt ol"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            onClick={() => {
              setScreen(id);
              setError("");
              setInfo("");
            }}
            className={cn(
              "rounded-xl px-3 py-2.5 text-sm font-semibold transition",
              screen === id
                ? "bg-zinc-900 text-white dark:bg-white dark:text-zinc-950"
                : "text-zinc-500",
            )}
          >
            {label}
          </button>
        ))}
      </div>
      ) : null}

      {mode === "student" || isForgot || isReset ? (
        <div className="mt-4 grid grid-cols-3 gap-1 rounded-2xl border border-zinc-200 p-1 dark:border-zinc-800">
          {(
            [
              ["google", "Google", Globe],
              ["email", "E-posta", Mail],
              ["phone", "Telefon", Phone],
            ] as const
          )
            .filter(([id]) => !(isForgot || isReset) || id !== "google")
            .map(([id, label, Icon]) => (
            <button
              key={id}
              type="button"
              onClick={() => {
                setChannel(id);
                setError("");
              }}
              className={cn(
                "flex flex-col items-center gap-1 rounded-xl px-2 py-2.5 text-[11px] font-semibold transition",
                channel === id
                  ? "bg-orange-500/15 text-orange-700 dark:text-orange-200"
                  : "text-zinc-500",
              )}
            >
              <Icon className="h-4 w-4" />
              {label}
            </button>
          ))}
        </div>
      ) : null}

      <p className="mt-4 text-sm text-zinc-600 dark:text-zinc-400">
        {isForgot
          ? "Kayıtlı e-posta veya telefonuna 6 haneli kod gönderilir."
          : isReset
            ? "E-postadaki kodu ve yeni şifreni gir."
            : mode === "teacher"
              ? "Sınıfını gör, hata röntgenini oku, kuponla öğrencileri otomatik ekle."
              : isRegister
                ? "Ad soyad, sınav hedefi ve e-posta / telefon / Google ile hesap aç."
                : "E-posta, telefon veya Google ile gir."}
      </p>

      <div className="mt-5 grid gap-3">
        {!isForgot && !isReset && (isRegister || mode === "teacher") && channel !== "google" ? (
          <label className="grid gap-1 text-xs font-medium text-zinc-600 dark:text-zinc-400">
            Ad soyad
            <Input
              value={displayName}
              onChange={(event) => setDisplayName(event.target.value)}
              placeholder={mode === "teacher" ? "Ayşe Hoca" : "Ali Yılmaz"}
              autoComplete="name"
            />
          </label>
        ) : null}

        {mode === "student" && isRegister && channel === "google" ? (
          <label className="grid gap-1 text-xs font-medium text-zinc-600 dark:text-zinc-400">
            Ad soyad
            <Input
              value={displayName}
              onChange={(event) => setDisplayName(event.target.value)}
              placeholder="Ali Yılmaz"
              autoComplete="name"
            />
          </label>
        ) : null}

        {mode === "student" && isRegister ? (
          <label className="grid gap-1 text-xs font-medium text-zinc-600 dark:text-zinc-400">
            Sınav hedefi
            <select
              value={examTarget}
              onChange={(event) =>
                setExamTarget(event.target.value as ExamTargetId | "")
              }
              className="h-10 w-full rounded-md border border-zinc-300 bg-white px-3 text-sm text-zinc-900 outline-none ring-orange-400/40 focus:ring-2 dark:border-zinc-700 dark:bg-zinc-950 dark:text-white"
            >
              {EXAM_FLAT.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
        ) : null}

        {mode === "teacher" && !isForgot && !isReset ? (
          <label className="grid gap-1 text-xs font-medium text-zinc-600 dark:text-zinc-400">
            Kullanıcı adı
            <Input
              value={userId}
              onChange={(event) => setUid(event.target.value)}
              placeholder="hoca_ayse"
              autoComplete="username"
            />
          </label>
        ) : null}

        {(mode === "student" || isForgot || isReset) && channel === "email" ? (
          <label className="grid gap-1 text-xs font-medium text-zinc-600 dark:text-zinc-400">
            E-posta
            <Input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="ornek@gmail.com"
              autoComplete="email"
            />
          </label>
        ) : null}

        {(mode === "student" || isForgot || isReset) && channel === "phone" ? (
          <label className="grid gap-1 text-xs font-medium text-zinc-600 dark:text-zinc-400">
            Telefon
            <Input
              type="tel"
              value={phone}
              onChange={(event) => setPhone(event.target.value)}
              placeholder="05xx xxx xx xx"
              autoComplete="tel"
            />
          </label>
        ) : null}

        {mode === "student" && channel === "google" && !isForgot && !isReset ? (
          <div className="rounded-xl border border-dashed border-zinc-300 px-3 py-3 dark:border-zinc-700">
            <GoogleSignInButton onCredential={onGoogle} disabled={busy} />
            {isRegister ? (
              <p className="mt-2 text-[11px] text-zinc-500">
                Önce ad soyad + sınav hedefi, sonra Google’a bas.
              </p>
            ) : null}
          </div>
        ) : null}

        {isReset ? (
          <>
            <label className="grid gap-1 text-xs font-medium text-zinc-600 dark:text-zinc-400">
              6 haneli kod
              <Input
                value={resetCode}
                onChange={(event) => setResetCode(event.target.value)}
                placeholder="123456"
                inputMode="numeric"
                autoComplete="one-time-code"
              />
            </label>
            <label className="grid gap-1 text-xs font-medium text-zinc-600 dark:text-zinc-400">
              Yeni şifre
              <Input
                type="password"
                value={newPassword}
                onChange={(event) => setNewPassword(event.target.value)}
                placeholder="En az 8 karakter"
                autoComplete="new-password"
              />
            </label>
          </>
        ) : null}

        {!isForgot && !isReset && (channel !== "google" || mode === "teacher") ? (
          <label className="grid gap-1 text-xs font-medium text-zinc-600 dark:text-zinc-400">
            Şifre
            <Input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="En az 8 karakter"
              autoComplete={isRegister ? "new-password" : "current-password"}
            />
          </label>
        ) : null}
      </div>

      {error ? <p className="mt-3 text-sm text-red-500">{error}</p> : null}
      {info ? <p className="mt-3 text-sm text-emerald-600 dark:text-emerald-300">{info}</p> : null}

      {(channel !== "google" || mode === "teacher" || isForgot || isReset) ? (
        <Button
          type="button"
          className="mt-5 h-12 w-full"
          disabled={busy || !canSubmit}
          onClick={() => void submit()}
        >
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
          {isForgot
            ? "Kod gönder"
            : isReset
              ? "Şifreyi güncelle"
              : isRegister
                ? "Kayıt ol"
                : mode === "teacher"
                  ? "Hoca paneline gir"
                  : "Giriş yap"}
        </Button>
      ) : null}

      {!isForgot && !isReset && !isRegister ? (
        <button
          type="button"
          className="mt-4 w-full rounded-xl border border-orange-300/70 bg-orange-50 px-3 py-3 text-sm font-semibold text-orange-800 transition hover:bg-orange-100 dark:border-orange-500/40 dark:bg-orange-950/40 dark:text-orange-200 dark:hover:bg-orange-950/70"
          onClick={() => {
            setScreen("forgot");
            setError("");
            setInfo("");
            setChannel(channel === "phone" ? "phone" : "email");
          }}
        >
          Şifremi unuttum
        </button>
      ) : null}

      <p className="mt-4 text-center text-xs text-zinc-500">
        {isForgot || isReset ? (
          <button
            type="button"
            className="font-semibold text-orange-600 underline-offset-2 hover:underline"
            onClick={() => {
              setScreen("login");
              setError("");
              setInfo("");
            }}
          >
            Girişe dön
          </button>
        ) : isRegister ? (
          <>
            Hesabın var mı?{" "}
            <button
              type="button"
              className="font-semibold text-orange-600 underline-offset-2 hover:underline"
              onClick={() => setScreen("login")}
            >
              Giriş yap
            </button>
          </>
        ) : (
          <>
            Yeni misin?{" "}
            <button
              type="button"
              className="font-semibold text-orange-600 underline-offset-2 hover:underline"
              onClick={() => setScreen("register")}
            >
              Kayıt ol
            </button>
          </>
        )}
      </p>
    </div>
  );
}
