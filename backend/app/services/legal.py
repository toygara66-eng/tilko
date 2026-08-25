"""Site yasal metinleri (gizlilik vb.) — admin panelden düzenlenir."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.database.models import SiteDocument

PRIVACY_KEY = "privacy"

DEFAULT_PRIVACY_TITLE = "Gizlilik Politikası"

DEFAULT_PRIVACY_BODY = """## 1. Kimiz?
Tilko (“uygulama”, “biz”), KPSS ve benzeri sınav hazırlığı için YouTube ders analizi, not, soru ve abonelik (Tilko Pro) hizmeti sunar. Web: tilko.site · Android paket: com.tilko.app. İletişim: developer@tilko.site.

## 2. Hangi verileri işleriz?
- **Hesap:** e-posta ve/veya telefon, ad soyad, şifre (hash’li), Google ile girişte Google kullanıcı kimliği ve e-posta.
- **Öğrenme verisi:** seçtiğin sınav hedefi, analiz notları, tuzak defteri, görevler, teşhis/check-up sonuçları, XP ve ilerleme.
- **Cihaz / güvenlik:** oturum jetonu, cihaz kimliği (anti-abuse), teknik loglar.
- **Ödeme:** Google Play abonelik doğrulaması için satın alma jetonu / sipariş bilgisi (kart numarası bizde saklanmaz; ödeme Google tarafından işlenir).
- **İsteğe bağlı:** geri bildirim metinleri, indirim kuponu kullanımı.

## 3. Verileri neden kullanırız?
- Hesap oluşturma, giriş ve şifre sıfırlama
- Ders analizi, not ve soru üretimi / saklama
- Kota, deneme süresi ve Tilko Pro abonelik yönetimi
- Güvenlik, kötüye kullanım ve destek
- Yasal yükümlülükler

## 4. Üçüncü taraflar
Hizmeti işletmek için sınırlı ölçüde üçüncü taraf altyapı kullanırız: barındırma (ör. bulut sunucu), e-posta gönderimi (şifre kodu), yapay zekâ modeli sağlayıcıları (analiz metni üretimi), Google (Giriş / Play Billing). Bu taraflara yalnızca gerekli veriler iletilir.

## 5. Saklama ve güvenlik
Veriler hizmetin sunulması için gerekli süre boyunca saklanır. Şifreler geri döndürülemez hash ile tutulur. Aktarımda HTTPS kullanılır. Yine de hiçbir sistem %100 riskten ari değildir.

## 6. Hakların
KVKK kapsamında verilerine erişme, düzeltme, silme ve işlemenin kısıtlanmasını talep edebilirsin. Talepler için developer@tilko.site adresine yaz. Hesabını uygulamadan da sildirmek için destek ile iletişime geçebilirsin.

## 7. Çocuklar
Tilko genel sınav hazırlığı içindir. 13 yaşından küçük çocuklardan bilerek veri toplamayız.

## 8. Değişiklikler
Bu metni güncelleyebiliriz. Önemli değişikliklerde uygulama veya site üzerinden bilgilendirme yapılır. Güncel metin her zaman https://tilko.site/gizlilik adresindedir.
"""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_privacy_doc(db: Session) -> SiteDocument:
    row = db.get(SiteDocument, PRIVACY_KEY)
    if row is None:
        row = SiteDocument(
            doc_key=PRIVACY_KEY,
            title=DEFAULT_PRIVACY_TITLE,
            body=DEFAULT_PRIVACY_BODY,
            updated_at=_utcnow(),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def get_privacy(db: Session) -> dict:
    row = ensure_privacy_doc(db)
    return {
        "ok": True,
        "key": row.doc_key,
        "title": (row.title or DEFAULT_PRIVACY_TITLE).strip() or DEFAULT_PRIVACY_TITLE,
        "body": (row.body or "").strip() or DEFAULT_PRIVACY_BODY,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def update_privacy(
    db: Session,
    *,
    title: str | None = None,
    body: str | None = None,
) -> dict:
    row = ensure_privacy_doc(db)
    if title is not None:
        name = (title or "").strip()[:200]
        if len(name) < 2:
            raise ValueError("Başlık en az 2 karakter olmalı.")
        row.title = name
    if body is not None:
        text = (body or "").strip()
        if len(text) < 20:
            raise ValueError("Metin en az 20 karakter olmalı.")
        if len(text) > 100_000:
            raise ValueError("Metin çok uzun (max 100000 karakter).")
        row.body = text
    row.updated_at = _utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    return get_privacy(db)
