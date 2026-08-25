import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Hesap silme talebi",
  description:
    "Tilko hesabınızı ve ilişkili verilerinizi silme talebi — adımlar ve saklama süreleri.",
  alternates: { canonical: "https://tilko.site/hesap-sil/" },
  robots: { index: true, follow: true },
};

export default function AccountDeletionPage() {
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
          Tilko · tilko.site
        </p>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900 dark:text-white">
          Hesap silme talebi
        </h1>
        <p className="text-xs text-zinc-500">
          Bu sayfa Google Play mağaza girişi için Tilko (geliştirici / uygulama
          adı: Tilko) hesap silme bilgilendirmesidir.
        </p>
      </header>

      <section className="space-y-2">
        <h2 className="text-base font-semibold text-zinc-900 dark:text-white">
          Hesabınızı nasıl silersiniz?
        </h2>
        <ol className="list-decimal space-y-2 pl-5">
          <li>
            <strong>developer@tilko.site</strong> adresine e-posta gönderin.
          </li>
          <li>
            Konu satırına yazın: <em>Tilko hesap silme talebi</em>
          </li>
          <li>
            Gövdede şunları belirtin: kayıtlı e-posta veya telefon, (varsa) ad
            soyad, Play’deki Google hesabı e-postası.
          </li>
          <li>
            Talebi, kayıtlı hesabınızdan veya o hesabın sahipliğini doğrulayan
            bir adresten gönderin.
          </li>
          <li>
            Talebinizi doğruladıktan sonra hesabı ve ilişkili verileri sileriz
            (aşağıdaki saklama istisnaları hariç).
          </li>
        </ol>
        <p>
          İletişim:{" "}
          <a
            className="text-orange-600 underline-offset-2 hover:underline dark:text-orange-300"
            href="mailto:developer@tilko.site?subject=Tilko%20hesap%20silme%20talebi"
          >
            developer@tilko.site
          </a>
        </p>
      </section>

      <section className="space-y-2">
        <h2 className="text-base font-semibold text-zinc-900 dark:text-white">
          Silinen veriler
        </h2>
        <ul className="list-disc space-y-1 pl-5">
          <li>Hesap kimliği, e-posta / telefon, ad soyad, şifre hash’i</li>
          <li>Google giriş kimliği bağlantısı (varsa)</li>
          <li>
            Öğrenme verisi: notlar, tuzak defteri, görevler, teşhis / check-up
            sonuçları, XP ve ilerleme
          </li>
          <li>Oturum jetonları ve cihaz / güvenlik kayıtları (hesaba bağlı)</li>
          <li>Geri bildirim ve kupon kullanım kayıtları (hesaba bağlı)</li>
          <li>
            Tilko Pro abonelik durumu uygulamada kapatılır; Google Play
            aboneliğini ayrıca Play Store → Abonelikler’den iptal etmeniz gerekir
          </li>
        </ul>
      </section>

      <section className="space-y-2">
        <h2 className="text-base font-semibold text-zinc-900 dark:text-white">
          Saklanabilecek veriler ve süreler
        </h2>
        <ul className="list-disc space-y-1 pl-5">
          <li>
            <strong>Yasal / güvenlik logları:</strong> kötüye kullanım ve yasal
            zorunluluk için en fazla <strong>90 gün</strong> (kişisel tanımlayıcılar
            mümkün olduğunca azaltılır).
          </li>
          <li>
            <strong>Ödeme kayıtları:</strong> kart bilgisi bizde tutulmaz; Google
            Play faturalama kayıtları Google’ın politikalarına tabidir.
          </li>
          <li>
            Yedeklerden tamamen temizlenme, teknik olarak birkaç gün daha
            sürebilir.
          </li>
        </ul>
      </section>

      <section className="space-y-2">
        <h2 className="text-base font-semibold text-zinc-900 dark:text-white">
          Süre
        </h2>
        <p>
          Doğrulanmış taleplerde hesabı genelde <strong>14 gün</strong> içinde
          sileriz. Gecikme olursa e-posta ile bilgilendiririz.
        </p>
      </section>

      <p className="text-xs text-zinc-500">
        Gizlilik politikası:{" "}
        <Link href="/gizlilik" className="underline-offset-2 hover:underline">
          tilko.site/gizlilik
        </Link>
      </p>
    </article>
  );
}
