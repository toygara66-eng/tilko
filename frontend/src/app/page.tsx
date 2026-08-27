"use client";

import { useEffect, useState } from "react";
import { HomeStage } from "@/components/home/home-stage";
import GirisPage from "@/app/giris/page";
import { isSignedIn } from "@/lib/auth";

export default function HomePage() {
  const [ready, setReady] = useState(false);
  const [signedIn, setSignedIn] = useState(false);

  useEffect(() => {
    setSignedIn(isSignedIn());
    setReady(true);
  }, []);

  if (!ready) {
    return (
      <div
        style={{
          minHeight: "50vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "#fb923c",
          fontSize: 14,
          fontWeight: 700,
        }}
      >
        TİLKO
      </div>
    );
  }

  // Capacitor'da /giris/ navigasyonu kırık olabiliyor → aynı ekranda giriş formu.
  if (!signedIn) {
    return <GirisPage />;
  }

  return <HomeStage />;
}
