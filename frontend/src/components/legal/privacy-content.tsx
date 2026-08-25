"use client";

import { useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { getPrivacyDocument } from "@/lib/api";

function renderInline(text: string) {
  const parts: ReactNode[] = [];
  const re = /\*\*(.+?)\*\*/g;
  let last = 0;
  let match: RegExpExecArray | null;
  let key = 0;
  while ((match = re.exec(text)) !== null) {
    if (match.index > last) {
      parts.push(text.slice(last, match.index));
    }
    parts.push(
      <strong key={`b-${key++}`} className="font-semibold text-zinc-900 dark:text-white">
        {match[1]}
      </strong>,
    );
    last = match.index + match[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

function PrivacyBody({ body }: { body: string }) {
  const lines = body.replace(/\r\n/g, "\n").split("\n");
  const blocks: ReactNode[] = [];
  let listItems: string[] = [];
  let key = 0;

  function flushList() {
    if (!listItems.length) return;
    blocks.push(
      <ul key={`ul-${key++}`} className="list-disc space-y-1 pl-5">
        {listItems.map((item, i) => (
          <li key={i}>{renderInline(item)}</li>
        ))}
      </ul>,
    );
    listItems = [];
  }

  for (const raw of lines) {
    const line = raw.trimEnd();
    const trimmed = line.trim();
    if (!trimmed) {
      flushList();
      continue;
    }
    if (trimmed.startsWith("## ")) {
      flushList();
      blocks.push(
        <h2
          key={`h-${key++}`}
          className="pt-2 text-base font-semibold text-zinc-900 dark:text-white"
        >
          {trimmed.slice(3).trim()}
        </h2>,
      );
      continue;
    }
    if (trimmed.startsWith("- ")) {
      listItems.push(trimmed.slice(2).trim());
      continue;
    }
    flushList();
    blocks.push(
      <p key={`p-${key++}`} className="text-sm leading-relaxed">
        {renderInline(trimmed)}
      </p>,
    );
  }
  flushList();
  return <div className="space-y-3">{blocks}</div>;
}

function formatUpdated(iso: string | null) {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleDateString("tr-TR", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

export function PrivacyContent() {
  const [title, setTitle] = useState("Gizlilik Politikası");
  const [body, setBody] = useState("");
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const data = await getPrivacyDocument();
        if (cancelled) return;
        setTitle(data.title || "Gizlilik Politikası");
        setBody(data.body || "");
        setUpdatedAt(data.updated_at);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Metin yüklenemedi");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const updatedLabel = formatUpdated(updatedAt);

  return (
    <article className="mx-auto max-w-2xl space-y-6 px-4 py-10 text-sm leading-relaxed text-zinc-700 dark:text-zinc-300">
      <p>
        <Link
          href="/giris"
          className="text-xs text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-200"
        >
          ← Giriş
        </Link>
      </p>
      <header className="space-y-2">
        <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-orange-600 dark:text-orange-300">
          Tilko
        </p>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900 dark:text-white">
          {title}
        </h1>
        {updatedLabel ? (
          <p className="text-xs text-zinc-500">Son güncelleme: {updatedLabel}</p>
        ) : null}
      </header>

      {loading ? (
        <p className="text-sm text-zinc-500">Yükleniyor…</p>
      ) : error ? (
        <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
      ) : (
        <PrivacyBody body={body} />
      )}
    </article>
  );
}
