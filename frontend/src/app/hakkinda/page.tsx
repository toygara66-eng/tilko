import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Tilko nedir? | KPSS YouTube ders analizi ve tuzak defteri",
  description:
    "Tilko (tilko.site): KPSS, YKS, LGS ve ÖABT için YouTube ders analizi, akıllı not, tuzak defteri, seviye teşhisi ve Tilko Pro. Türkçe sınav koçu uygulaması.",
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
  ],
  alternates: { canonical: "https://tilko.site/hakkinda/" },
  openGraph: {
    title: "Tilko — KPSS YouTube ders analizi",
    description:
      "YouTube dersini not ve ÖSYM tuzağına çevir. Tilko ile KPSS / YKS hazırlığı.",
    url: "https://tilko.site/hakkinda/",
    siteName: "Tilko",
    locale: "tr_TR",
    type: "website",
  },
};

const jsonLd = {
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "Organization",
      name: "Tilko",
      alternateName: ["TİLKO", "tilko.site"],
      url: "https://tilko.site",
      logo: "https://tilko.site/logo.png",
      email: "developer@tilko.site",
      sameAs: ["https://tilko.site"],
    },
    {
      "@type": "SoftwareApplication",
      name: "Tilko",
      applicationCategory: "EducationalApplication",
      operatingSystem: "Android, Web",
      url: "https://tilko.site",
      description:
        "KPSS ve benzeri sınavlar için YouTube ders analizi, not, tuzak defteri ve abonelik (Tilko Pro).",
      offers: {
        "@type": "Offer",
        price: "0",
        priceCurrency: "TRY",
        description: "Ücretsiz deneme; Tilko Pro isteğe bağlı",
      },
      author: { "@type": "Organization", name: "Tilko" },
    },
    {
      "@type": "WebSite",
      name: "Tilko",
      url: "https://tilko.site",
      inLanguage: "tr-TR",
      potentialAction: {
        "@type": "SearchAction",
        target: "https://tilko.site/hakkinda/?q={search_term_string}",
        "query-input": "required name=search_term_string",
      },
    },
  ],
};

export default function AboutPage() {
  return (
    <article className="mx-auto max-w-2xl space-y-8 px-4 py-10 text-sm leading-relaxed text-zinc-700 dark:text-zinc-300">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
      <p>
        <Link
          href="/giris"
          className="text-xs text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-200"
        >
          ← Giriş
        </Link>
      </p>
      <header className="space-y-3">
        <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-orange-600 dark:text-orange-300">
          Tilko · tilko.site
        </p>
        <h1 className="text-3xl font-semibold tracking-tight text-zinc-900 dark:text-white">
          Tilko nedir?
        </h1>
        <p className="text-base text-zinc-600 dark:text-zinc-400">
          Tilko, KPSS, YKS, LGS ve ÖABT adayları için YouTube derslerini analiz
          edip not, soru ve ÖSYM tarzı tuzak üreten Türkçe bir sınav koçu
          uygulamasıdır.
        </p>
      </header>

      <section className="space-y-2">
        <h2 className="text-base font-semibold text-zinc-900 dark:text-white">
          Ne işe yarar?
        </h2>
        <ul className="list-disc space-y-1.5 pl-5">
          <li>
            YouTube ders linkini yapıştırırsın; Tilko dersi özetler, not çıkarır.
          </li>
          <li>
            Kolay kaçan noktaları <strong>tuzak defterine</strong> kaydedersin.
          </li>
          <li>
            İlk girişte <strong>seviye teşhisi</strong>; sonra haftalık check-up
            ile gelişimi ölçersin.
          </li>
          <li>
            Görevler, XP ve tekrar hatırlatmalarıyla düzenli çalışmanı sürdürür.
          </li>
          <li>
            Hocalar sınıf / öğrenci paneliyle takip edebilir.
          </li>
        </ul>
      </section>

      <section className="space-y-2">
        <h2 className="text-base font-semibold text-zinc-900 dark:text-white">
          Kimler için?
        </h2>
        <p>
          KPSS lisans / önlisans / ortaöğretim, YKS, LGS, ÖABT ve benzeri merkezi
          sınavlara hazırlanan öğrenciler ile onları yönlendiren hocalar için
          tasarlandı.
        </p>
      </section>

      <section className="space-y-2">
        <h2 className="text-base font-semibold text-zinc-900 dark:text-white">
          Tilko Pro
        </h2>
        <p>
          Ücretsiz kullanımın yanında Google Play üzerinden{" "}
          <strong>Tilko Pro</strong> aboneliği (haftalık, aylık, yıllık) ile kota
          ve Pro özellikler açılır. Android paket adı:{" "}
          <code className="rounded bg-zinc-100 px-1 dark:bg-zinc-900">
            com.tilko.site
          </code>
          .
        </p>
      </section>

      <section className="space-y-2">
        <h2 className="text-base font-semibold text-zinc-900 dark:text-white">
          Resmi adresler
        </h2>
        <ul className="list-disc space-y-1 pl-5">
          <li>
            Site:{" "}
            <a className="text-orange-600 hover:underline dark:text-orange-300" href="https://tilko.site">
              https://tilko.site
            </a>
          </li>
          <li>
            Giriş:{" "}
            <Link className="text-orange-600 hover:underline dark:text-orange-300" href="/giris">
              /giris
            </Link>
          </li>
          <li>
            Gizlilik:{" "}
            <Link className="text-orange-600 hover:underline dark:text-orange-300" href="/gizlilik">
              /gizlilik
            </Link>
          </li>
          <li>
            İletişim:{" "}
            <a
              className="text-orange-600 hover:underline dark:text-orange-300"
              href="mailto:developer@tilko.site"
            >
              developer@tilko.site
            </a>
          </li>
        </ul>
      </section>

      <p>
        <Link
          href="/giris"
          className="inline-flex rounded-full bg-orange-500 px-4 py-2 text-sm font-semibold text-zinc-950"
        >
          Tilko’ya giriş yap
        </Link>
      </p>
    </article>
  );
}
