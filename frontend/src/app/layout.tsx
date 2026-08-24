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
  title: "TİLKO",
  description: "YouTube ders analizi, tuzak defteri ve Ebbinghaus tekrarları",
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
