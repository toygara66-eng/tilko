"""Günlük Tilki mottoları — rütbe + sınav hedefine göre sabit günlük seçim."""

from __future__ import annotations

import hashlib
from datetime import date

from sqlalchemy.orm import Session

from app.services.exams import exam_of, family_of, label_for, today_istanbul
from app.services.penalty import get_or_create_user
from app.services.ranks import RANK_ACEMI, RANK_ALFA, RANK_KIDEMLI, RANK_KURNAZ, address_for

COMMON = [
    "Kurnazlık gürültü değil {title}. Sessiz çöz, netin konuşsun.",
    "Bugünün yemi dünün tuzağı. Aynı şıkka iki kez düşme.",
    "Tilki koşmaz, iz sürer. Bir kavram, bir tekrar, bir zafer.",
    "Aceleye gelen sazan olur. 60 saniye, sonra şık.",
    "Defter boşsa av boş. Yanlışını yaz, yarına silah bırak.",
    "Zafere giden yol kısa değil; kurnaz olan yorulmaz.",
]

BY_RANK = {
    RANK_ACEMI: [
        "Kuyruk yeni kıpırdadı {title}. Bugün bir tuzak çöz, yarın alışkanlık olur.",
        "Acemi olmak utanç değil, durmak utanç. Bir video, bir net.",
        "İlk izler taze {title}. ÖSYM’nin yemini şimdiden kokla.",
        "Yavaş değil, uyanık avlan. Bugün tek bir ayrımı ezberle.",
    ],
    RANK_KURNAZ: [
        "Prenslik heves değil {title}. Çeldiriciyi gördüğün an bırakma.",
        "Kurnaz olan çok soru çözmez, doğru tuzağı çözer.",
        "Sürü sağa kaçarken sen sola bak {title}. Klasik yem orada.",
        "İsmi prens, işi iz sürmek. Bugün bir istisnayı kilitle.",
    ],
    RANK_KIDEMLI: [
        "Kıdem, ezber yığını değil {title}. Tuzak haritasını taze tut.",
        "Sürü seni izliyor. Bugün sazan olma, örnek ol.",
        "Yüksek rütbe yüksek temizlik ister. Defterde kalanı bugün avla.",
        "Biliyorsun sandığın yerde ÖSYM bekler. Bir kez daha bak.",
    ],
    RANK_ALFA: [
        "Alfa tilki gürültü çıkarmaz {title}. Net konuşur, sürü susar.",
        "Zirve kaygandır. Bugün de aynı disiplini tak, tahtı kaptırma.",
        "Sürü arkanda. Sen yemi gör, onlar senin izini görsün.",
        "Alfa olmak bitmek değil. Her gün bir çeldirici daha.",
    ],
}

BY_FAMILY = {
    "kpss": [
        "ÖSYM aynı yemi atar. Sen aynı tilki değilsin.",
        "Yıl, ferman, organ. Üçlü tuzak — bugün birini kilitle.",
        "Vatandaşlık ezberi değil, kaydırma haritası. Şıkkı kokla.",
        "GY-GK sabır işi. Bir madde, bir istisna, bir net.",
    ],
    "yks": [
        "TYT sabır, AYT kurnazlık. Bugün bir kavramı kilitle.",
        "Formülü ezberleme, tuzağını gör. Yakın şık en tehlikeli.",
        "Paragraf koşu değil {title}. Kökü oku, sonra şıkka in.",
        "YKS sazanlığı: bildiğini sandığın yer. Bir kez daha bak.",
    ],
    "oabt": [
        "Alan bilgisi ezber değil, tuzak haritası {title}.",
        "Pedagoji şıkkı şişman görünür. Kökteki fiile bak.",
        "Müfredat kalabalığına dalma. Bugün bir basamağı netleştir.",
        "ÖABT’de sazan, yakın kuramı karıştırandır. Ayır, geç.",
    ],
    "lgs": [
        "Kütle yoğunluk değildir {title}. Somut düşün, tuzak çözülür.",
        "Ortaokul bitmez, tilki bitirir. Bugün bir kazığı sök.",
        "Kök kısa, şık kurnaz. Acele etme, LGS orada bekler.",
        "Sade soru en tehlikeli yem. Bir kez daha oku.",
    ],
    "other": [
        "Sınavın adı değişir, tilki aynı kalır. İzi sür.",
        "Yakın kavram, klasik yem. Bugün bir çifti ayır.",
        "Kurnazlık kurum tanımaz {title}. Şıkkı kokla, geç.",
    ],
}


def _pool(title: str, exam_target: str) -> list[str]:
    family = family_of(exam_target)
    rows = list(COMMON)
    rows.extend(BY_RANK.get(title) or BY_RANK[RANK_ACEMI])
    rows.extend(BY_FAMILY.get(family) or BY_FAMILY["other"])
    return rows


def quote_for(user_id: str, title: str, exam_target: str, day: date | None = None) -> str:
    stamp = day or today_istanbul()
    pool = _pool(title, exam_target)
    raw = f"{user_id}|{stamp.isoformat()}|{title}|{exam_target}"
    index = int(hashlib.sha1(raw.encode("utf-8")).hexdigest(), 16) % len(pool)
    return pool[index].replace("{title}", title)


def daily_quote(db: Session, user_id: str) -> dict:
    uid = (user_id or "").strip()
    if not uid:
        raise ValueError("Kullanıcı kimliği gerekli.")
    get_or_create_user(db, uid)
    title = address_for(db, uid)
    exam = exam_of(db, uid)
    day = today_istanbul()
    return {
        "user_id": uid,
        "quote": quote_for(uid, title, exam, day),
        "title": title,
        "exam_target": exam,
        "exam_label": label_for(exam),
        "date": day.isoformat(),
    }
