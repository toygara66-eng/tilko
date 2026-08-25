import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Gizlilik Politikası · TİLKO",
  description: "Tilko uygulaması gizlilik politikası ve kişisel verilerin işlenmesi.",
};

export default function PrivacyPage() {
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
          Gizlilik Politikası
        </h1>
        <p className="text-xs text-zinc-500">Son güncelleme: 25 Ağustos 2026</p>
      </header>

      <section className="space-y-2">
        <h2 className="text-base font-semibold text-zinc-900 dark:text-white">
          1. Kimiz?
        </h2>
        <p>
          Tilko (“uygulama”, “biz”), KPSS ve benzeri sınav hazırlığı için YouTube
          ders analizi, not, soru ve abonelik (Tilko Pro) hizmeti sunar. Web:
          tilko.site · Android paket: com.tilko.app. İletişim:{" "}
          <a
            className="text-orange-600 underline-offset-2 hover:underline dark:text-orange-300"
            href="mailto:developer@tilko.site"
          >
            developer@tilko.site
          </a>
          .
        </p>
      </section>

      <section className="space-y-2">
        <h2 className="text-base font-semibold text-zinc-900 dark:text-white">
          2. Hangi verileri işleriz?
        </h2>
        <ul className="list-disc space-y-1 pl-5">
          <li>
            <strong>Hesap:</strong> e-posta ve/veya telefon, ad soyad, şifre
            (hash’li), Google ile girişte Google kullanıcı kimliği ve e-posta.
          </li>
          <li>
            <strong>Öğrenme verisi:</strong> seçtiğin sınav hedefi, analiz
            notları, tuzak defteri, görevler, teşhis/check-up sonuçları, XP ve
            ilerleme.
          </li>
          <li>
            <strong>Cihaz / güvenlik:</strong> oturum jetonu, cihaz kimliği
            (anti-abuse), teknik loglar.
          </li>
          <li>
            <strong>Ödeme:</strong> Google Play abonelik doğrulaması için satın
            alma jetonu / sipariş bilgisi (kart numarası bizde saklanmaz; ödeme
            Google tarafından işlenir).
          </li>
          <li>
            <strong>İsteğe bağlı:</strong> geri bildirim metinleri, indirim
            kuponu kullanımı.
          </li>
        </ul>
      </section>

      <section className="space-y-2">
        <h2 className="text-base font-semibold text-zinc-900 dark:text-white">
          3. Verileri neden kullanırız?
        </h2>
        <ul className="list-disc space-y-1 pl-5">
          <li>Hesap oluşturma, giriş ve şifre sıfırlama</li>
          <li>Ders analizi, not ve soru üretimi / saklama</li>
          <li>Kota, deneme süresi ve Tilko Pro abonelik yönetimi</li>
          <li>Güvenlik, kötüye kullanım ve destek</li>
          <li>Yasal yükümlülükler</li>
        </ul>
      </section>

      <section className="space-y-2">
        <h2 className="text-base font-semibold text-zinc-900 dark:text-white">
          4. Üçüncü taraflar
        </h2>
        <p>
          Hizmeti işletmek için sınırlı ölçüde üçüncü taraf altyapı kullanırız:
          barındırma (ör. bulut sunucu), e-posta gönderimi (şifre kodu), yapay
          zekâ modeli sağlayıcıları (analiz metni üretimi), Google (Giriş /
          Play Billing). Bu taraflara yalnızca gerekli veriler iletilir.
        </p>
      </section>

      <section className="space-y-2">
        <h2 className="text-base font-semibold text-zinc-900 dark:text-white">
          5. Saklama ve güvenlik
        </h2>
        <p>
          Veriler hizmetin sunulması için gerekli süre boyunca saklanır. Şifreler
          geri döndürülemez hash ile tutulur. Aktarımda HTTPS kullanılır. Yine de
          hiçbir sistem %100 riskten ari değildir.
        </p>
      </section>

      <section className="space-y-2">
        <h2 className="text-base font-semibold text-zinc-900 dark:text-white">
          6. Hakların
        </h2>
        <p>
          KVKK kapsamında verilerine erişme, düzeltme, silme ve işlemenin
          kısıtlanmasını talep edebilirsin. Talepler için{" "}
          <a
            className="text-orange-600 underline-offset-2 hover:underline dark:text-orange-300"
            href="mailto:developer@tilko.site"
          >
            developer@tilko.site
          </a>{" "}
          adresine yaz. Hesabını uygulamadan da sildirmek için destek ile
          iletişime geçebilirsin.
        </p>
      </section>

      <section className="space-y-2">
        <h2 className="text-base font-semibold text-zinc-900 dark:text-white">
          7. Çocuklar
        </h2>
        <p>
          Tilko genel sınav hazırlığı içindir. 13 yaşından küçük çocuklardan
          bilerek veri toplamayız.
        </p>
      </section>

      <section className="space-y-2">
        <h2 className="text-base font-semibold text-zinc-900 dark:text-white">
          8. Değişiklikler
        </h2>
        <p>
          Bu metni güncelleyebiliriz. Önemli değişikliklerde uygulama veya site
          üzerinden bilgilendirme yapılır. Güncel metin her zaman{" "}
          <span className="font-mono text-xs">https://tilko.site/gizlilik</span>{" "}
          adresindedir.
        </p>
      </section>

      <p className="pt-4 text-xs text-zinc-400">
        Play Console / mağaza listing için gizlilik URL’si:{" "}
        <span className="font-mono">https://tilko.site/gizlilik</span>
      </p>
    </article>
  );
}
