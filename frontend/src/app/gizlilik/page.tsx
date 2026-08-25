import type { Metadata } from "next";
import { PrivacyContent } from "@/components/legal/privacy-content";

export const metadata: Metadata = {
  title: "Gizlilik Politikası · TİLKO",
  description: "Tilko uygulaması gizlilik politikası ve kişisel verilerin işlenmesi.",
};

export default function PrivacyPage() {
  return <PrivacyContent />;
}
