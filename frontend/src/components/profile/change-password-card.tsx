"use client";

import { useState, type FormEvent } from "react";
import { KeyRound, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PasswordInput } from "@/components/ui/password-input";
import { changePassword } from "@/lib/api";
import { setAuthSecret } from "@/lib/auth";

export function ChangePasswordCard() {
  const [open, setOpen] = useState(false);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState("");

  function resetForm() {
    setCurrentPassword("");
    setNewPassword("");
    setConfirm("");
    setError("");
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setDone("");
    if (newPassword.length < 8) {
      setError("Yeni şifre en az 8 karakter olmalı.");
      return;
    }
    if (newPassword !== confirm) {
      setError("Yeni şifreler eşleşmiyor.");
      return;
    }
    setBusy(true);
    try {
      const data = await changePassword({
        current_password: currentPassword,
        new_password: newPassword,
      });
      setAuthSecret(newPassword);
      setDone(data.message || "Şifren güncellendi.");
      resetForm();
      setOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Şifre değiştirilemedi");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="rounded-2xl border border-orange-400/40 bg-white/55 p-5 backdrop-blur-xl dark:bg-zinc-950/45">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-orange-600 dark:text-orange-300">
            Hesap
          </p>
          <p className="mt-1 text-sm font-medium text-zinc-800 dark:text-zinc-100">
            Şifre yenile
          </p>
          <p className="mt-1 text-xs text-zinc-500">
            Mevcut şifreni değiştir veya Google hesabına şifre ekle.
          </p>
        </div>
        {!open ? (
          <Button
            type="button"
            variant="outline"
            className="h-10 shrink-0"
            onClick={() => {
              setDone("");
              setError("");
              setOpen(true);
            }}
          >
            <KeyRound className="h-4 w-4" />
            Şifre değiştir
          </Button>
        ) : null}
      </div>

      {done ? (
        <p className="mt-3 text-sm text-emerald-700 dark:text-emerald-300">{done}</p>
      ) : null}

      {open ? (
        <form onSubmit={submit} className="mt-4 space-y-3">
          <div>
            <label className="mb-1 block text-xs font-medium text-zinc-500">
              Mevcut şifre
            </label>
            <PasswordInput
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              autoComplete="current-password"
              placeholder="Varsa mevcut şifre (Google-only ise boş)"
              disabled={busy}
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-zinc-500">
              Yeni şifre
            </label>
            <PasswordInput
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              autoComplete="new-password"
              placeholder="En az 8 karakter"
              disabled={busy}
              required
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-zinc-500">
              Yeni şifre (tekrar)
            </label>
            <PasswordInput
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              autoComplete="new-password"
              placeholder="Tekrar yaz"
              disabled={busy}
              required
            />
          </div>
          {error ? <p className="text-sm text-red-500">{error}</p> : null}
          <div className="flex flex-wrap gap-2">
            <Button type="submit" className="h-10" disabled={busy}>
              {busy ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Kaydediliyor…
                </>
              ) : (
                "Kaydet"
              )}
            </Button>
            <Button
              type="button"
              variant="outline"
              className="h-10"
              disabled={busy}
              onClick={() => {
                setOpen(false);
                resetForm();
              }}
            >
              Vazgeç
            </Button>
          </div>
        </form>
      ) : null}
    </section>
  );
}
