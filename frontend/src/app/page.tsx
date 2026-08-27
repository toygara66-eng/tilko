"use client";

import { useEffect, useState } from "react";
import { HomeStage } from "@/components/home/home-stage";
import { isSignedIn } from "@/lib/auth";
import { hardNavigate } from "@/lib/path";
import { Loader2 } from "lucide-react";

export default function HomePage() {
  const [ok, setOk] = useState(false);

  useEffect(() => {
    if (isSignedIn()) {
      setOk(true);
      return;
    }
    hardNavigate("/giris");
  }, []);

  if (!ok) {
    return (
      <div
        style={{
          minHeight: "60vh",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 12,
          padding: 24,
        }}
      >
        <Loader2 className="h-6 w-6 animate-spin text-orange-500" />
        <p style={{ color: "#a1a1aa", fontSize: 13 }}>Giriş ekranına yönlendiriliyor…</p>
        <a
          href="/giris/"
          style={{
            marginTop: 8,
            color: "#fb923c",
            fontWeight: 700,
            fontSize: 14,
          }}
        >
          Giriş / Kayıt
        </a>
      </div>
    );
  }

  return <HomeStage />;
}
