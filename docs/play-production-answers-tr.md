# Play Production Access — örnek cevaplar

Testers Community formu için. **Türkçe varsayılan** bilinçli olarak korundu (hedef kitle Türkiye’deki KPSS adayları).

## 1) Test kullanıcıları nasıl bulundu?

Paid testing provider (Testers Community) ile çok cihaz/SDK testi yaptık. Ek olarak hedef kitlemiz olan KPSS adaylarından gerçek kullanım geri bildirimi topladık.

## 2) Test kullanıcısı bulmak ne kadar kolaydı?

Easy

## 3) Kapalı testte tester etkileşimi

Testers işlevsellik, kullanılabilirlik ve iyileştirme alanları hakkında geri bildirim verdi. ASO, şifre görünürlüğü, onboarding turu ve performans iyileştirmeleri uygulandı.

## 4) Geri bildirim özeti ve toplama yötesi

Geri bildirim: ASO optimizasyonu, şifre alanında göz ikonu, daha etkileşimli uygulama turu, not yükleme hızı. Toplama: Testers Community raporu, uygulama içi geri bildirim formu (ampul ikonu), kapalı test anketleri.

## 5) Hedef kitle

KPSS ve merkezi sınavlara hazırlanan adaylar; YouTube ile çalışan, tekrar ve tuzak analizi isteyen öğrenciler.

## 6) Kullanıcıya sağladığı değer

YouTube dersini not + ÖSYM tarzı soruya çevirir; tuzak defteri, günlük görev ve seviye teşhisi ile pasif izlemeyi aktif tekrara dönüştürür.

## 7) İlk yıl kurulum beklentisi

10k – 100k

## 8) Kapalı testten sonra yapılan değişiklikler

- Play Store açıklaması ASO için yenilendi (`docs/play-store-aso-tr.md`)
- Şifre alanına göster/gizle (göz ikonu) eklendi
- İlk kullanım için etkileşimli 5 adımlı uygulama turu
- Notlarım: oturum bazlı yükleme (daha hızlı arşiv)
- Soru ekranında cevap sızıntısı azaltıldı
- **Varsayılan dil Türkçe** (hedef kitle TR); İngilizce varsayılan yapılmadı

## 9) Production’a hazır olduğuna nasıl karar verildi?

Çok cihaz testinde kritik crash yok. Billing 9.x, targetSdk 36 uyumlu. Tester önerileri uygulandı; stabilite ve UX doğrulandı.

## 10) Bu sefer farklı ne yapıldı?

Çeşitli tester grubu, ASO metinleri, kullanıcı geri bildirimine dayalı UX (şifre, tur, performans) ve Play policy uyumluluğu (billing, API 36) önceliklendirildi.
