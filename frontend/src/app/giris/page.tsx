"use client";

import { useState } from "react";
import { Loader2, GraduationCap, School } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { TilkoLogo } from "@/components/brand/tilko-logo";
import { GoogleSignInButton } from "@/components/auth/google-sign-in";
import { loginAccount, loginWithGoogle, registerAccount } from "@/lib/api";
import { setAuthMode, setAuthSecret, setStoredRole, setToken } from "@/lib/auth";
import { getUserId, setUserId } from "@/lib/user";
import { cn } from "@/lib/utils";

type Mode = "student" | "teacher";

export default function GirisPage() {
  const [mode, setMode] = useState<Mode>("student");
  const [userId, setUid] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [registering, setRegistering] = useState(false);

  function finishSession(data: {
    access_token: string;
    role: string;
    user_id: string;
    dashboard?: string;
  }, passwordForStore?: string) {
    setToken(data.access_token);
    if (passwordForStore) setAuthSecret(passwordForStore);
    else setAuthMode("google");
    setStoredRole(data.role);
    setUserId(data.user_id);
    window.location.assign(data.dashboard || (data.role === "teacher" ? "/hoca" : "/"));
  }

  async function submit(isRegister: boolean) {
    setBusy(true);
    setError("");
    const payload = {
      user_id: userId.trim(),
      password,
      role: mode,
      display_name: mode === "teacher" ? displayName.trim() : "",
    };
    try {
      const data = isRegister
        ? await registerAccount(payload)
        : await loginAccount(payload);
      finishSession(data, password);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Giriş yapılamadı");
    } finally {
      setBusy(false);
    }
  }

  async function onGoogle(idToken: string) {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const guest = getUserId();
      const data = await loginWithGoogle({
        id_token: idToken,
        role: mode === "teacher" ? "teacher" : "student",
        display_name: mode === "teacher" ? displayName.trim() : "",
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
    <div className="mx-auto flex min-h-[80vh] w-full max-w-md flex-col justify-center px-4">
      <div className="mb-6 flex items-center gap-3">
        <TilkoLogo size={40} />
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-orange-600">
            TİLKO
          </p>
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-900 dark:text-white">
            Giriş
          </h1>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 rounded-2xl border border-zinc-200 bg-white/70 p-1 dark:border-zinc-800 dark:bg-zinc-950/50">
        {(
          [
            ["student", "Öğrenci Girişi", GraduationCap],
            ["teacher", "Hoca Girişi", School],
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

      <p className="mt-4 text-sm text-zinc-600 dark:text-zinc-400">
        {mode === "teacher"
          ? "Sınıfını gör, hata röntgenini oku, kuponla öğrencileri otomatik ekle."
          : "Tuzak defterin, sazan avın ve teşhisin burada."}
      </p>

      <div className="mt-5">
        <GoogleSignInButton onCredential={onGoogle} disabled={busy} />
      </div>

      <div className="my-5 flex items-center gap-3 text-[11px] uppercase tracking-[0.18em] text-zinc-400">
        <span className="h-px flex-1 bg-zinc-200 dark:bg-zinc-800" />
        veya
        <span className="h-px flex-1 bg-zinc-200 dark:bg-zinc-800" />
      </div>

      <div className="grid gap-3">
        {mode === "teacher" ? (
          <label className="grid gap-1 text-xs font-medium text-zinc-600 dark:text-zinc-400">
            Görünen ad
            <Input
              value={displayName}
              onChange={(event) => setDisplayName(event.target.value)}
              placeholder="Ayşe Hoca"
            />
          </label>
        ) : null}
        <label className="grid gap-1 text-xs font-medium text-zinc-600 dark:text-zinc-400">
          Kullanıcı adı
          <Input
            value={userId}
            onChange={(event) => setUid(event.target.value)}
            placeholder={mode === "teacher" ? "hoca_ayse" : "aday_ali"}
            autoComplete="username"
          />
        </label>
        <label className="grid gap-1 text-xs font-medium text-zinc-600 dark:text-zinc-400">
          Şifre
          <Input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder="En az 8 karakter"
            autoComplete={registering ? "new-password" : "current-password"}
          />
        </label>
      </div>

      {error ? <p className="mt-3 text-sm text-red-500">{error}</p> : null}

      <div className="mt-5 grid gap-2">
        <Button
          type="button"
          className="h-12"
          disabled={busy || userId.trim().length < 3 || password.length < 8}
          onClick={() => {
            setRegistering(false);
            void submit(false);
          }}
        >
          {busy && !registering ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
          {mode === "teacher" ? "Hoca paneline gir" : "Öğrenci olarak gir"}
        </Button>
        <Button
          type="button"
          variant="outline"
          className="h-12"
          disabled={busy || userId.trim().length < 3 || password.length < 8}
          onClick={() => {
            setRegistering(true);
            void submit(true);
          }}
        >
          {busy && registering ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
          Hesap oluştur
        </Button>
      </div>
    </div>
  );
}
