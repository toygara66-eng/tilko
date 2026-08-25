import type { Metadata } from "next";
import type { ReactNode } from "react";
import Script from "next/script";
import { Caveat, Inter, Kalam } from "next/font/google";
import { AppShell } from "@/components/layout/app-shell";
import { ErrorBoundary } from "@/components/error-boundary";
import "./globals.css";

const inter = Inter({
  subsets: ["latin", "latin-ext"],
  variable: "--font-inter",
});

const caveat = Caveat({
  subsets: ["latin", "latin-ext"],
  variable: "--font-caveat",
});

const kalam = Kalam({
  weight: ["400", "700"],
  subsets: ["latin", "latin-ext"],
  variable: "--font-kalam",
});

export const metadata: Metadata = {
  metadataBase: new URL("https://tilko.site"),
  title: {
    default: "Tilko — KPSS YouTube ders analizi ve tuzak defteri",
    template: "%s · Tilko",
  },
  description:
    "Tilko (tilko.site): KPSS, YKS, LGS ve ÖABT için YouTube ders analizi, akıllı not, tuzak defteri, seviye teşhisi ve Tilko Pro. Türkçe sınav koçu.",
  applicationName: "Tilko",
  keywords: [
    "Tilko",
    "tilko.site",
    "KPSS",
    "YouTube ders analizi",
    "tuzak defteri",
    "ÖSYM",
    "YKS",
    "LGS",
    "ÖABT",
    "Tilko Pro",
    "sınav hazırlık",
  ],
  authors: [{ name: "Tilko", url: "https://tilko.site" }],
  creator: "Tilko",
  publisher: "Tilko",
  alternates: {
    canonical: "https://tilko.site/",
  },
  openGraph: {
    type: "website",
    locale: "tr_TR",
    url: "https://tilko.site/",
    siteName: "Tilko",
    title: "Tilko — KPSS YouTube ders analizi",
    description:
      "YouTube dersini not ve ÖSYM tuzağına çevir. Tilko ile KPSS / YKS hazırlığı.",
    images: [{ url: "/logo.png", width: 512, height: 512, alt: "Tilko" }],
  },
  twitter: {
    card: "summary",
    title: "Tilko — KPSS YouTube ders analizi",
    description:
      "YouTube ders analizi, tuzak defteri ve Tilko Pro. tilko.site",
    images: ["/logo.png"],
  },
  robots: {
    index: true,
    follow: true,
    googleBot: { index: true, follow: true },
  },
  category: "education",
  icons: {
    icon: [
      { url: "/favicon.ico", sizes: "any" },
      { url: "/favicon-48x48.png", sizes: "48x48", type: "image/png" },
      { url: "/favicon-96x96.png", sizes: "96x96", type: "image/png" },
      { url: "/favicon-144x144.png", sizes: "144x144", type: "image/png" },
      { url: "/favicon-192x192.png", sizes: "192x192", type: "image/png" },
    ],
    apple: [{ url: "/apple-touch-icon.png", sizes: "180x180", type: "image/png" }],
    shortcut: ["/favicon.ico"],
  },
};

export const viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({
  children,
}: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="tr" className={`dark ${inter.variable} ${caveat.variable} ${kalam.variable}`} suppressHydrationWarning>
      <body className={`${inter.className} font-sans`}>
        <Script
          id="tilko-theme"
          strategy="beforeInteractive"
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var t=localStorage.getItem("tilko_theme");var d=t?t==="dark":!window.matchMedia("(prefers-color-scheme: light)").matches;document.documentElement.classList.toggle("dark",d);document.documentElement.style.colorScheme=d?"dark":"light";}catch(e){}})();`,
          }}
        />
        <ErrorBoundary>
          <AppShell>{children}</AppShell>
        </ErrorBoundary>
      </body>
    </html>
  );
}
