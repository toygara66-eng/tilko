"use client";

import { useEffect, useRef, useState } from "react";

const CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || "";

type GisCredentialResponse = {
  credential?: string;
};

type GoogleAccountsId = {
  initialize: (config: {
    client_id: string;
    callback: (response: GisCredentialResponse) => void;
    auto_select?: boolean;
    ux_mode?: string;
  }) => void;
  renderButton: (
    parent: HTMLElement,
    options: {
      theme?: string;
      size?: string;
      width?: number;
      text?: string;
      shape?: string;
      locale?: string;
    },
  ) => void;
  prompt?: () => void;
};

declare global {
  interface Window {
    google?: {
      accounts?: {
        id?: GoogleAccountsId;
      };
    };
  }
}

let scriptPromise: Promise<void> | null = null;

function loadGis(): Promise<void> {
  if (typeof window === "undefined") return Promise.resolve();
  if (window.google?.accounts?.id) return Promise.resolve();
  if (scriptPromise) return scriptPromise;
  scriptPromise = new Promise((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>(
      'script[src="https://accounts.google.com/gsi/client"]',
    );
    if (existing) {
      existing.addEventListener("load", () => resolve());
      existing.addEventListener("error", () => reject(new Error("Google script yüklenemedi")));
      if (window.google?.accounts?.id) resolve();
      return;
    }
    const script = document.createElement("script");
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.defer = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Google script yüklenemedi"));
    document.head.appendChild(script);
  });
  return scriptPromise;
}

export function GoogleSignInButton({
  onCredential,
  disabled,
}: {
  onCredential: (idToken: string) => void | Promise<void>;
  disabled?: boolean;
}) {
  const host = useRef<HTMLDivElement>(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const cb = useRef(onCredential);
  cb.current = onCredential;

  useEffect(() => {
    if (!CLIENT_ID) {
      setError("");
      return;
    }
    let cancelled = false;
    loadGis()
      .then(() => {
        if (cancelled || !host.current || !window.google?.accounts?.id) return;
        window.google.accounts.id.initialize({
          client_id: CLIENT_ID,
          callback: (response) => {
            const token = String(response.credential || "").trim();
            if (token) void cb.current(token);
          },
          auto_select: false,
          ux_mode: "popup",
        });
        host.current.innerHTML = "";
        window.google.accounts.id.renderButton(host.current, {
          theme: "outline",
          size: "large",
          width: 320,
          text: "continue_with",
          shape: "pill",
          locale: "tr",
        });
        setReady(true);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Google yüklenemedi");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!CLIENT_ID) {
    return (
      <p className="rounded-xl border border-dashed border-zinc-300 px-3 py-3 text-center text-xs text-zinc-500 dark:border-zinc-700">
        Google ile giriş için{" "}
        <code className="text-[10px]">NEXT_PUBLIC_GOOGLE_CLIENT_ID</code> ve sunucuda{" "}
        <code className="text-[10px]">GOOGLE_CLIENT_ID</code> ayarla.
      </p>
    );
  }

  return (
    <div className={disabled ? "pointer-events-none opacity-50" : undefined}>
      <div ref={host} className="flex min-h-[44px] justify-center" />
      {!ready && !error ? (
        <p className="mt-1 text-center text-xs text-zinc-500">Google hazırlanıyor…</p>
      ) : null}
      {error ? <p className="mt-1 text-center text-xs text-red-500">{error}</p> : null}
    </div>
  );
}

export function googleClientConfigured() {
  return Boolean(CLIENT_ID);
}
