"""KPSS seviye teşhisi ve haftalık gelişim check-up."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import (
    DiagnosticIpMark,
    DiagnosticTest,
    ProgressCheckup,
    User,
    UserBaseline,
)
from app.services.penalty import get_or_create_user
from app.services.ranks import RANK_ACEMI, address_for

logger = logging.getLogger(__name__)

ISTANBUL_OFFSET = timezone(timedelta(hours=3))
CHECKUP_DAYS = 7
BASELINE_COUNT = 8
CHECKUP_COUNT = 5


def is_registered_account(user: User) -> bool:
    """Şifreli hesap = başka kullanıcı; IP atlaması uygulanmaz."""
    return bool((getattr(user, "password_hash", "") or "").strip())


def mark_diagnostic_ip(db: Session, ip_hash: str, user_id: str) -> None:
    digest = (ip_hash or "").strip()
    if not digest or not user_id:
        return
    row = db.get(DiagnosticIpMark, digest)
    if row:
        row.source_user_id = user_id
        row.completed_at = datetime.now(timezone.utc)
        return
    db.add(
        DiagnosticIpMark(
            ip_hash=digest,
            source_user_id=user_id,
            completed_at=datetime.now(timezone.utc),
        )
    )


def _adopt_baseline_from_source(db: Session, user: User, source_user_id: str) -> bool:
    source = get_baseline(db, source_user_id)
    donor = db.get(User, source_user_id)
    if source is None and not (donor and donor.is_tested):
        return False
    user.is_tested = True
    if donor:
        user.baseline_score = float(donor.baseline_score or 0)
        if not float(getattr(user, "target_score", 0) or 0):
            user.target_score = float(getattr(donor, "target_score", 0) or 0)
    if source is None:
        return True
    user.baseline_score = float(source.score or user.baseline_score or 0)
    baseline = get_baseline(db, user.user_id)
    if baseline is None:
        baseline = UserBaseline(user_id=user.user_id)
        db.add(baseline)
    baseline.score = float(source.score or 0)
    baseline.weak_topics = source.weak_topics or "[]"
    baseline.strong_topics = source.strong_topics or "[]"
    baseline.analysis_summary = source.analysis_summary or ""
    baseline.net_range = source.net_range or ""
    baseline.topic_breakdown = source.topic_breakdown or "{}"
    return True


def maybe_skip_diagnostic_for_ip(db: Session, user: User, ip_hash: str) -> bool:
    """Aynı IP'den teşhis geçmişse misafir oturumu tekrar sorma."""
    if user.is_tested:
        return True
    if is_registered_account(user):
        return False
    digest = (ip_hash or "").strip()
    if not digest:
        return False
    mark = db.get(DiagnosticIpMark, digest)
    if mark is None or not mark.source_user_id:
        return False
    if mark.source_user_id == user.user_id:
        user.is_tested = True
        return True
    return _adopt_baseline_from_source(db, user, mark.source_user_id)


def diagnostic_system(title: str, exam_target: str | None = None) -> str:
    from app.services.exams import label_for, prompt_block

    return (
        "Sen TİLKO'nun kurnaz sınav koçusun. Öğrenciye "
        f"yalnızca '{title}' diye hitap et. Başka lakap kullanma. "
        f"Hedef sınav: {label_for(exam_target)}. {prompt_block(exam_target)} "
        "Ton: cam gibi net, biraz sataşkan, asla küçümseyici değil. Türkçe yaz. "
        "Çıktı SADECE geçerli JSON. Markdown yok."
    )


DIAGNOSTIC_SYSTEM = diagnostic_system(RANK_ACEMI)

QUESTION_BANK = [
    {
        "id": "d-tarih-tanzimat",
        "topic": "Tarih",
        "question_text": "Tanzimat Fermanı hangi yılda ilan edilmiştir?",
        "options": {"A": "1839", "B": "1856", "C": "1876", "D": "1908", "E": "1923"},
        "correct": "A",
    },
    {
        "id": "d-tarih-mesrutiyet",
        "topic": "Tarih",
        "question_text": "Kanun-i Esasi hangi olayla yürürlüğe girmiştir?",
        "options": {
            "A": "Tanzimat",
            "B": "Islahat",
            "C": "I. Meşrutiyet",
            "D": "II. Meşrutiyet",
            "E": "Cumhuriyet’in ilanı",
        },
        "correct": "C",
    },
    {
        "id": "d-tarih-lozan",
        "topic": "Tarih",
        "question_text": "Lozan Antlaşması hangi yılda imzalanmıştır?",
        "options": {"A": "1920", "B": "1921", "C": "1922", "D": "1923", "E": "1924"},
        "correct": "D",
    },
    {
        "id": "d-tarih-saltanat",
        "topic": "Tarih",
        "question_text": "Saltanat hangi tarihte kaldırılmıştır?",
        "options": {
            "A": "23 Nisan 1920",
            "B": "1 Kasım 1922",
            "C": "29 Ekim 1923",
            "D": "3 Mart 1924",
            "E": "20 Ocak 1921",
        },
        "correct": "B",
    },
    {
        "id": "d-vat-anayasa",
        "topic": "Vatandaşlık",
        "question_text": "Türkiye’de yürürlükteki Anayasa hangi yılda kabul edilmiştir?",
        "options": {"A": "1921", "B": "1924", "C": "1961", "D": "1982", "E": "2017"},
        "correct": "D",
    },
    {
        "id": "d-vat-yasama",
        "topic": "Vatandaşlık",
        "question_text": "1982 Anayasası’na göre yasama yetkisi kime aittir?",
        "options": {
            "A": "Cumhurbaşkanı",
            "B": "Bakanlar Kurulu",
            "C": "TBMM",
            "D": "Anayasa Mahkemesi",
            "E": "Hâkimler ve Savcılar Kurulu",
        },
        "correct": "C",
    },
    {
        "id": "d-vat-sistem",
        "topic": "Vatandaşlık",
        "question_text": "2017 Anayasa değişikliği ile hangi hükümet sistemine geçilmiştir?",
        "options": {
            "A": "Parlamenter sistem",
            "B": "Yarı başkanlık",
            "C": "Cumhurbaşkanlığı hükümet sistemi",
            "D": "Meclis hükümeti",
            "E": "Anayasal monarşi",
        },
        "correct": "C",
    },
    {
        "id": "d-cog-agri",
        "topic": "Coğrafya",
        "question_text": "Türkiye’nin en yüksek dağı hangisidir?",
        "options": {
            "A": "Erciyes",
            "B": "Süphan",
            "C": "Ağrı",
            "D": "Kaçkar",
            "E": "Uludağ",
        },
        "correct": "C",
    },
    {
        "id": "d-cog-bogaz",
        "topic": "Coğrafya",
        "question_text": "İstanbul ve Çanakkale boğazları hangi denizleri birbirine bağlar?",
        "options": {
            "A": "Akdeniz – Ege",
            "B": "Karadeniz – Marmara – Ege",
            "C": "Marmara – Akdeniz",
            "D": "Ege – Adriyatik",
            "E": "Karadeniz – Hazar",
        },
        "correct": "B",
    },
    {
        "id": "d-cog-iklim",
        "topic": "Coğrafya",
        "question_text": "Akdeniz ikliminin Türkiye’deki tipik özelliği hangisidir?",
        "options": {
            "A": "Yazlar serin ve yağışlı, kışlar kurak",
            "B": "Yazlar sıcak ve kurak, kışlar ılık ve yağışlı",
            "C": "Yıl boyu bol yağış ve orman",
            "D": "Kışın don, yazın muson yağmuru",
            "E": "Çöl etkisi ve gece-gündüz farkı yok",
        },
        "correct": "B",
    },
    {
        "id": "d-tur-unlu",
        "topic": "Türkçe",
        "question_text": "Aşağıdaki sözcüklerden hangisinde büyük ünlü uyumu yoktur?",
        "options": {
            "A": "kapı",
            "B": "anne",
            "C": "yıldız",
            "D": "elma",
            "E": "kitap",
        },
        "correct": "B",
    },
    {
        "id": "d-tur-fiil",
        "topic": "Türkçe",
        "question_text": "“Okuldan çıkınca eve gittim.” cümlesinde “çıkınca” sözcüğünün görevi nedir?",
        "options": {
            "A": "Zarf-fiil (ulaç)",
            "B": "Sıfat-fiil (ortaç)",
            "C": "İsim-fiil (mastar)",
            "D": "Edat",
            "E": "Bağlaç",
        },
        "correct": "A",
    },
    {
        "id": "d-tarih-tbmm",
        "topic": "Tarih",
        "question_text": "TBMM hangi tarihte açılmıştır?",
        "options": {
            "A": "19 Mayıs 1919",
            "B": "23 Nisan 1920",
            "C": "30 Ağustos 1922",
            "D": "29 Ekim 1923",
            "E": "3 Mart 1924",
        },
        "correct": "B",
    },
    {
        "id": "d-cog-akarsu",
        "topic": "Coğrafya",
        "question_text": "Van Gölü hangi havza tipindedir?",
        "options": {
            "A": "Açık havza",
            "B": "Kapalı havza",
            "C": "Delta havzası",
            "D": "Karstik havza",
            "E": "Gelgit havzası",
        },
        "correct": "B",
    },
]

for _item in QUESTION_BANK:
    topic = _item["topic"]
    exams = ["kpss"]
    if topic in {"Türkçe", "Tarih", "Coğrafya"}:
        exams.extend(["yks", "lgs", "other"])
    _item["exams"] = exams

QUESTION_BANK.extend(
    [
        {
            "id": "d-mat-oran",
            "topic": "Matematik",
            "exams": ["yks", "lgs", "other"],
            "question_text": "12 sayısının %25’i kaçtır?",
            "options": {"A": "2", "B": "3", "C": "4", "D": "5", "E": "6"},
            "correct": "B",
        },
        {
            "id": "d-mat-denklem",
            "topic": "Matematik",
            "exams": ["yks", "lgs", "other"],
            "question_text": "2x + 6 = 14 ise x kaçtır?",
            "options": {"A": "2", "B": "3", "C": "4", "D": "5", "E": "8"},
            "correct": "C",
        },
        {
            "id": "d-fiz-newton",
            "topic": "Fizik",
            "exams": ["yks"],
            "question_text": "Newton’un ikinci yasası hangi bağıntıdır?",
            "options": {
                "A": "F = m · a",
                "B": "E = m · c²",
                "C": "P = F / A",
                "D": "V = I · R",
                "E": "p = m · v",
            },
            "correct": "A",
        },
        {
            "id": "d-fiz-isik",
            "topic": "Fizik",
            "exams": ["yks"],
            "question_text": "Işık boşlukta yaklaşık kaç km/s hızla yayılır?",
            "options": {
                "A": "3×10⁴",
                "B": "3×10⁶",
                "C": "3×10⁸",
                "D": "3×10¹⁰",
                "E": "330",
            },
            "correct": "C",
        },
        {
            "id": "d-kim-atom",
            "topic": "Kimya",
            "exams": ["yks"],
            "question_text": "Bir atomun kimliğini belirleyen parçacık hangisidir?",
            "options": {"A": "Elektron", "B": "Nötron", "C": "Proton", "D": "Foton", "E": "Pozitron"},
            "correct": "C",
        },
        {
            "id": "d-kim-su",
            "topic": "Kimya",
            "exams": ["yks"],
            "question_text": "Suyun kimyasal formülü nedir?",
            "options": {"A": "H₂O", "B": "CO₂", "C": "NaCl", "D": "O₂", "E": "CH₄"},
            "correct": "A",
        },
        {
            "id": "d-bio-hucre",
            "topic": "Biyoloji",
            "exams": ["yks"],
            "question_text": "Bitki hücresinde olup hayvan hücresinde olmayan organel hangisidir?",
            "options": {
                "A": "Mitokondri",
                "B": "Kloroplast",
                "C": "Ribozom",
                "D": "Çekirdek",
                "E": "Golgi",
            },
            "correct": "B",
        },
        {
            "id": "d-fen-fotosentez",
            "topic": "Fen",
            "exams": ["lgs"],
            "question_text": "Fotosentezde bitki hangi gazı üretir?",
            "options": {"A": "Azot", "B": "Karbondioksit", "C": "Oksijen", "D": "Metan", "E": "Helyum"},
            "correct": "C",
        },
        {
            "id": "d-fen-kutle",
            "topic": "Fen",
            "exams": ["lgs"],
            "question_text": "Kütle birimi hangisidir?",
            "options": {"A": "Newton", "B": "Joule", "C": "Kilogram", "D": "Watt", "E": "Pascal"},
            "correct": "C",
        },
        {
            "id": "d-ink-19mayis",
            "topic": "İnkılap",
            "exams": ["lgs"],
            "question_text": "Mustafa Kemal Samsun’a hangi tarihte çıkmıştır?",
            "options": {
                "A": "23 Nisan 1920",
                "B": "19 Mayıs 1919",
                "C": "30 Ağustos 1922",
                "D": "29 Ekim 1923",
                "E": "1 Kasım 1922",
            },
            "correct": "B",
        },
        {
            "id": "d-ink-cumhuriyet",
            "topic": "İnkılap",
            "exams": ["lgs"],
            "question_text": "Cumhuriyet hangi tarihte ilan edilmiştir?",
            "options": {
                "A": "23 Nisan 1920",
                "B": "1 Kasım 1922",
                "C": "29 Ekim 1923",
                "D": "3 Mart 1924",
                "E": "19 Mayıs 1919",
            },
            "correct": "C",
        },
        {
            "id": "d-oabt-bloom",
            "topic": "Ölçme-değerlendirme",
            "exams": ["oabt"],
            "question_text": "Bloom taksonomisinin bilişsel alandaki en üst basamağı hangisidir?",
            "options": {
                "A": "Bilgi",
                "B": "Kavrama",
                "C": "Uygulama",
                "D": "Analiz",
                "E": "Yaratma / sentez",
            },
            "correct": "E",
        },
        {
            "id": "d-oabt-gecerlik",
            "topic": "Ölçme-değerlendirme",
            "exams": ["oabt"],
            "question_text": "Bir testin ölçmek istediğini ölçmesi hangi kavramdır?",
            "options": {
                "A": "Güvenirlik",
                "B": "Geçerlik",
                "C": "Ayırt edicilik",
                "D": "Madde güçlüğü",
                "E": "Normallik",
            },
            "correct": "B",
        },
        {
            "id": "d-oabt-pavlova",
            "topic": "Öğrenme kuramı",
            "exams": ["oabt"],
            "question_text": "Klasik koşullanma kimle özdeşleşir?",
            "options": {
                "A": "Skinner",
                "B": "Pavlov",
                "C": "Piaget",
                "D": "Vygotsky",
                "E": "Bandura",
            },
            "correct": "B",
        },
        {
            "id": "d-oabt-yakin",
            "topic": "Öğrenme kuramı",
            "exams": ["oabt"],
            "question_text": "Yakınsak gelişim alanı (ZPD) kimin kavramıdır?",
            "options": {
                "A": "Piaget",
                "B": "Bruner",
                "C": "Vygotsky",
                "D": "Ausubel",
                "E": "Gagné",
            },
            "correct": "C",
        },
        {
            "id": "d-oabt-alan",
            "topic": "Alan bilgisi",
            "exams": ["oabt"],
            "question_text": "ÖABT’de asıl ağırlık hangi alandadır?",
            "options": {
                "A": "Genel kültür",
                "B": "Yabancı dil",
                "C": "Alan bilgisi ve alan eğitimi",
                "D": "Spor",
                "E": "Güncel olaylar",
            },
            "correct": "C",
        },
        {
            "id": "d-oabt-program",
            "topic": "Alan bilgisi",
            "exams": ["oabt"],
            "question_text": "Öğretim programının omurgası hangisidir?",
            "options": {
                "A": "Ders kitabı kapağı",
                "B": "Kazanımlar / yeterlikler",
                "C": "Okul bahçesi",
                "D": "Kantin menüsü",
                "E": "Nöbet çizelgesi",
            },
            "correct": "B",
        },
        {
            "id": "d-gen-osym",
            "topic": "Genel kültür",
            "exams": ["other"],
            "question_text": "Türkiye’de merkezi sınavları hangi kurum yapar?",
            "options": {
                "A": "MEB İlçe",
                "B": "YÖK",
                "C": "ÖSYM",
                "D": "TÜBİTAK",
                "E": "Dışişleri",
            },
            "correct": "C",
        },
        {
            "id": "d-gen-anayasa",
            "topic": "Genel kültür",
            "exams": ["other"],
            "question_text": "Türkiye Cumhuriyeti’nin yönetim biçimi nedir?",
            "options": {
                "A": "Meşrutiyet",
                "B": "Cumhuriyet",
                "C": "Monarşi",
                "D": "Federasyon",
                "E": "Emirlik",
            },
            "correct": "B",
        },
    ]
)

VIDEO_RECS = {
    "Tarih": [
        {
            "title": "KPSS Tarih — inkılap ve Osmanlı tuzakları",
            "topic": "Tarih",
            "url": "https://www.youtube.com/results?search_query=KPSS+tarih+inkilap+ders+anlatimi",
        }
    ],
    "Vatandaşlık": [
        {
            "title": "KPSS Vatandaşlık — Anayasa ve sistem",
            "topic": "Vatandaşlık",
            "url": "https://www.youtube.com/results?search_query=KPSS+vatandaslik+anayasa+ders",
        }
    ],
    "Coğrafya": [
        {
            "title": "KPSS Coğrafya — iklim, yerşekli, Türkiye",
            "topic": "Coğrafya",
            "url": "https://www.youtube.com/results?search_query=KPSS+cografya+turkiye+iklim",
        }
    ],
    "Türkçe": [
        {
            "title": "KPSS Türkçe — dil bilgisi tuzakları",
            "topic": "Türkçe",
            "url": "https://www.youtube.com/results?search_query=KPSS+turkce+dil+bilgisi+ders",
        },
        {
            "title": "YKS Türkçe — paragraf ve dil bilgisi",
            "topic": "Türkçe",
            "url": "https://www.youtube.com/results?search_query=TYT+turkce+paragraf+ders",
        },
    ],
    "Matematik": [
        {
            "title": "YKS Matematik — TYT temel",
            "topic": "Matematik",
            "url": "https://www.youtube.com/results?search_query=TYT+matematik+ders+anlatimi",
        }
    ],
    "Fizik": [
        {
            "title": "AYT Fizik — kavram ve öncül tuzakları",
            "topic": "Fizik",
            "url": "https://www.youtube.com/results?search_query=AYT+fizik+ders+anlatimi",
        }
    ],
    "Kimya": [
        {
            "title": "AYT Kimya — tepkime ve kavram",
            "topic": "Kimya",
            "url": "https://www.youtube.com/results?search_query=AYT+kimya+ders+anlatimi",
        }
    ],
    "Biyoloji": [
        {
            "title": "AYT Biyoloji — sistemler",
            "topic": "Biyoloji",
            "url": "https://www.youtube.com/results?search_query=AYT+biyoloji+ders+anlatimi",
        }
    ],
    "Fen": [
        {
            "title": "LGS Fen — fotosentez ve kuvvet",
            "topic": "Fen",
            "url": "https://www.youtube.com/results?search_query=LGS+fen+bilimleri+ders",
        }
    ],
    "İnkılap": [
        {
            "title": "LGS İnkılap — 19 Mayıs ve Cumhuriyet",
            "topic": "İnkılap",
            "url": "https://www.youtube.com/results?search_query=LGS+inkilap+tarihi+ders",
        }
    ],
    "Alan bilgisi": [
        {
            "title": "ÖABT alan bilgisi",
            "topic": "Alan bilgisi",
            "url": "https://www.youtube.com/results?search_query=OABT+alan+bilgisi+ders",
        }
    ],
    "Ölçme-değerlendirme": [
        {
            "title": "ÖABT ölçme ve değerlendirme",
            "topic": "Ölçme-değerlendirme",
            "url": "https://www.youtube.com/results?search_query=OABT+olcme+degerlendirme",
        }
    ],
    "Öğrenme kuramı": [
        {
            "title": "ÖABT öğrenme psikolojisi",
            "topic": "Öğrenme kuramı",
            "url": "https://www.youtube.com/results?search_query=OABT+ogrenme+psikolojisi",
        }
    ],
}

BANK_BY_ID = {item["id"]: item for item in QUESTION_BANK}


def today_istanbul() -> date:
    try:
        return datetime.now(ZoneInfo("Europe/Istanbul")).date()
    except ZoneInfoNotFoundError:
        return datetime.now(ISTANBUL_OFFSET).date()


def _loads(raw: str, fallback):
    try:
        return json.loads(raw or "")
    except json.JSONDecodeError:
        return fallback


def public_question(item: dict) -> dict:
    return {
        "id": item["id"],
        "topic": item["topic"],
        "question_text": item["question_text"],
        "options": item["options"],
    }


def _seeded_order(user_id: str, salt: str, pool: list[dict] | None = None) -> list[dict]:
    digest = hashlib.sha1(f"{user_id}:{salt}".encode("utf-8")).hexdigest()
    ranked = sorted(
        pool or QUESTION_BANK,
        key=lambda item: hashlib.sha1(f"{digest}:{item['id']}".encode()).hexdigest(),
    )
    return ranked


def bank_for(exam_target: str | None) -> list[dict]:
    from app.services.exams import matches_exam, subjects_for

    subjects = set(subjects_for(exam_target))
    tagged = [item for item in QUESTION_BANK if matches_exam(item, exam_target)]
    if subjects:
        filtered = [item for item in tagged if item.get("topic") in subjects]
        if filtered:
            tagged = filtered
    return tagged


def exam_for(
    user_id: str,
    kind: str,
    exam_target: str | None = None,
    db: Session | None = None,
) -> list[dict]:
    from app.services.exams import exam_of, subjects_for

    if exam_target is None and db is not None:
        exam_target = exam_of(db, user_id)
    pool = bank_for(exam_target)
    kind = (kind or "baseline").strip().lower()
    if kind == "checkup":
        picked = _seeded_order(user_id, str(today_istanbul()), pool)[:CHECKUP_COUNT]
    else:
        by_topic: dict[str, list[dict]] = {}
        for item in pool:
            by_topic.setdefault(item["topic"], []).append(item)
        picked = []
        topics = subjects_for(exam_target) or ("Tarih", "Vatandaşlık", "Coğrafya", "Türkçe")
        for topic in topics:
            topic_pool = by_topic.get(topic) or []
            picked.extend(topic_pool[:2])
            if len(picked) >= BASELINE_COUNT:
                break
        if len(picked) < BASELINE_COUNT:
            leftover = [item for item in pool if item not in picked]
            picked.extend(leftover[: BASELINE_COUNT - len(picked)])
        picked = picked[:BASELINE_COUNT]
    return [public_question(item) for item in picked]


def grade(answers: list[dict]) -> dict:
    rows = []
    topic_hits: dict[str, list[bool]] = {}
    for raw in answers:
        qid = str(raw.get("question_id") or raw.get("id") or "")
        chosen = str(raw.get("chosen") or "").strip().upper()[:1]
        if not qid or not chosen:
            continue
        item = BANK_BY_ID.get(qid)
        if not item:
            continue
        ok = chosen == item["correct"]
        topic_hits.setdefault(item["topic"], []).append(ok)
        rows.append(
            {
                "question_id": qid,
                "topic": item["topic"],
                "chosen": chosen,
                "correct": item["correct"],
                "is_correct": ok,
            }
        )
    total = len(rows) or 1
    right = sum(1 for row in rows if row["is_correct"])
    score = round(100.0 * right / total, 1)
    breakdown = {}
    weak = []
    strong = []
    for topic, hits in topic_hits.items():
        ratio = sum(hits) / len(hits)
        breakdown[topic] = {
            "correct": sum(hits),
            "total": len(hits),
            "ratio": round(ratio, 2),
        }
        if ratio < 0.67:
            weak.append(topic)
        elif ratio >= 0.8:
            strong.append(topic)
    if not weak and breakdown:
        weakest = min(breakdown.items(), key=lambda pair: pair[1]["ratio"])
        if weakest[1]["ratio"] < 1:
            weak = [weakest[0]]
    return {
        "answers": rows,
        "score": score,
        "correct_count": right,
        "total": len(rows),
        "weak_topics": weak,
        "strong_topics": strong,
        "topic_breakdown": breakdown,
    }


def net_range_for(score: float) -> str:
    if score >= 85:
        return "85-95"
    if score >= 70:
        return "75-85"
    if score >= 55:
        return "65-80"
    if score >= 40:
        return "55-70"
    return "45-60"


def fallback_summary(
    graded: dict,
    *,
    checkup: bool,
    previous: dict | None,
    title: str = RANK_ACEMI,
) -> dict:
    weak = graded["weak_topics"]
    strong = graded["strong_topics"]
    score = graded["score"]
    target = max(85, int(score) + 15)
    weak_txt = ", ".join(weak) if weak else "belirgin bir açık yok"
    strong_txt = ", ".join(strong) if strong else "henüz net bir kale yok"
    if checkup and previous:
        delta = round(score - float(previous.get("score") or 0), 1)
        if delta > 2:
            summary = (
                f"Helal olsun {title}, bu hafta netlerin {delta:.0f} puan uçtu. "
                f"{strong_txt} tarafın oturuyor; {weak_txt} hâlâ tuzak. Rota güncellendi."
            )
        elif delta < -2:
            summary = (
                f"Hey {title}, skor {abs(delta):.0f} puan geriledi. Panik yok — "
                f"{weak_txt} tuzaklarına bu hafta Tuzak Defteri’nden giriyoruz."
            )
        else:
            summary = (
                f"Hey {title}, tempo aynı, skor {score:.0f}. {weak_txt} hâlâ açık; "
                f"{strong_txt} korunacak. Küçük tekrar, büyük fark."
            )
    else:
        summary = (
            f"Analiz tamamlandı {title}! {weak_txt} tuzaklarında biraz zayıfsın "
            f"ama {strong_txt} sağlam. Seni {target}+ puana taşıyacak rota oluşturuldu."
        )
    return {
        "summary": summary,
        "weak_topics": weak,
        "strong_topics": strong,
        "net_range": net_range_for(score),
        "target_score": target,
    }


def llm_baseline(graded: dict, title: str = RANK_ACEMI, exam_target: str | None = None) -> dict:
    from app.services.llm import complete_json
    from app.services.exams import label_for

    prompt = f"""Öğrencinin teşhis sınavı sonucu (hedef: {label_for(exam_target)}):
skor: {graded['score']}
doğru: {graded['correct_count']}/{graded['total']}
konu kırılımı: {json.dumps(graded['topic_breakdown'], ensure_ascii=False)}
zayıf: {graded['weak_topics']}
güçlü: {graded['strong_topics']}

2-3 cümlelik TİLKO üslubunda özet yaz. Öğrenciye '{title}' diye hitap et.
Zayıf konuyu ve sağlam konuyu söyle. 85+ rota vaadi ver.

JSON:
{{
  "summary": "...",
  "weak_topics": ["Coğrafya"],
  "strong_topics": ["Tarih"],
  "net_range": "75-85",
  "target_score": 85
}}
"""
    try:
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                complete_json,
                diagnostic_system(title, exam_target),
                prompt,
                0.5,
                "diagnostic",
            )
            try:
                data = future.result(timeout=12)
            except FuturesTimeout as exc:
                logger.warning("Teşhis LLM 12sn aştı, yerelde özetlendi: %s", exc)
                return fallback_summary(graded, checkup=False, previous=None, title=title)
    except Exception as exc:
        logger.warning("Teşhis LLM düştü, yerelde özetlendi: %s", exc)
        return fallback_summary(graded, checkup=False, previous=None, title=title)
    summary = str(data.get("summary") or "").strip()
    if not summary:
        return fallback_summary(graded, checkup=False, previous=None, title=title)
    weak = data.get("weak_topics") or graded["weak_topics"]
    strong = data.get("strong_topics") or graded["strong_topics"]
    return {
        "summary": summary,
        "weak_topics": [str(item) for item in weak],
        "strong_topics": [str(item) for item in strong],
        "net_range": str(data.get("net_range") or net_range_for(graded["score"])),
        "target_score": int(data.get("target_score") or 85),
    }


def llm_checkup(graded: dict, previous: dict | None, title: str = RANK_ACEMI, exam_target: str | None = None) -> dict:
    from app.services.llm import complete_json
    from app.services.exams import label_for

    prev_score = previous.get("score") if previous else None
    prompt = f"""Haftalık check-up karşılaştırması (hedef: {label_for(exam_target)}):
şimdiki skor: {graded['score']}
önceki skor: {prev_score}
şimdiki zayıf: {graded['weak_topics']}
önceki zayıf: {(previous or {}).get('weak_topics')}
kırılım: {json.dumps(graded['topic_breakdown'], ensure_ascii=False)}

2 cümle. Geçen haftaya/check-up’a göre net değişimini söyle. Motive et, sataş.
Öğrenciye '{title}' diye hitap et. İyileşme varsa 'Helal olsun {title}' de.

JSON:
{{
  "improvement_summary": "...",
  "weak_topics": ["Coğrafya"],
  "score_delta": 8
}}
"""
    try:
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                complete_json,
                diagnostic_system(title, exam_target),
                prompt,
                0.5,
                "checkup",
            )
            try:
                data = future.result(timeout=12)
            except FuturesTimeout:
                data = {}
    except Exception as exc:
        logger.warning("Check-up LLM düştü, yerelde özetlendi: %s", exc)
        local = fallback_summary(graded, checkup=True, previous=previous, title=title)
        return {
            "improvement_summary": local["summary"],
            "weak_topics": local["weak_topics"],
        }
    text = str(data.get("improvement_summary") or data.get("summary") or "").strip()
    if not text:
        local = fallback_summary(graded, checkup=True, previous=previous, title=title)
        return {
            "improvement_summary": local["summary"],
            "weak_topics": local["weak_topics"],
        }
    weak = data.get("weak_topics") or graded["weak_topics"]
    return {
        "improvement_summary": text,
        "weak_topics": [str(item) for item in weak],
    }


def get_baseline(db: Session, user_id: str) -> UserBaseline | None:
    return db.get(UserBaseline, user_id)


def last_checkup(db: Session, user_id: str) -> ProgressCheckup | None:
    return db.scalars(
        select(ProgressCheckup)
        .where(ProgressCheckup.user_id == user_id)
        .order_by(ProgressCheckup.checkup_date.desc(), ProgressCheckup.id.desc())
    ).first()


def checkup_due_for(user: User, last: ProgressCheckup | None, baseline: UserBaseline | None) -> bool:
    if not user.is_tested:
        return False
    today = today_istanbul()
    if last:
        anchor = last.checkup_date
    elif baseline and baseline.updated_at:
        stamp = baseline.updated_at
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        anchor = stamp.date()
    else:
        return True
    if (today - anchor).days >= CHECKUP_DAYS:
        return True
    if today.day == 1 and (anchor.year, anchor.month) != (today.year, today.month):
        return True
    return False


def baseline_payload(row: UserBaseline | None) -> dict | None:
    if row is None:
        return None
    return {
        "score": float(row.score or 0),
        "weak_topics": _loads(row.weak_topics, []),
        "strong_topics": _loads(row.strong_topics, []),
        "analysis_summary": row.analysis_summary,
        "net_range": row.net_range,
        "topic_breakdown": _loads(row.topic_breakdown, {}),
    }


def status(db: Session, user_id: str, ip_hash: str = "") -> dict:
    user = get_or_create_user(db, user_id)
    if not user.is_tested and ip_hash:
        maybe_skip_diagnostic_for_ip(db, user, ip_hash)
    base = get_baseline(db, user_id)
    last = last_checkup(db, user_id)
    due = checkup_due_for(user, last, base)
    return {
        "is_tested": bool(user.is_tested),
        "baseline_score": float(user.baseline_score or 0),
        "checkup_due": due,
        "last_checkup_date": last.checkup_date.isoformat() if last else None,
        "baseline": baseline_payload(base),
        "weak_topics": _loads(base.weak_topics, []) if base else [],
        "recommended_videos": recommended_videos(
            _loads(base.weak_topics, []) if base else [],
            getattr(user, "exam_target", "") or None,
        ),
    }


def recommended_videos(weak_topics: list[str], exam_target: str | None = None) -> list[dict]:
    from app.services.exams import family_of, subjects_for

    family = family_of(exam_target)
    allowed = set(subjects_for(exam_target))

    def ok(item: dict) -> bool:
        title = (item.get("title") or "").upper()
        if family == "yks":
            return "KPSS" not in title and "LGS" not in title and "OABT" not in title and "ÖABT" not in title
        if family == "kpss":
            return "TYT" not in title and "AYT" not in title and "YKS" not in title and "LGS" not in title
        if family == "lgs":
            return "LGS" in title or "İNKILAP" in title
        if family == "oabt":
            return "OABT" in title or "ÖABT" in title or "ALAN" in title or "ÖLÇME" in title
        return True

    topics = [topic for topic in (weak_topics or []) if not allowed or topic in allowed]
    if not topics:
        topics = list(allowed) or list(VIDEO_RECS.keys())
    out = []
    seen = set()
    for topic in topics:
        for item in VIDEO_RECS.get(topic, []):
            if not ok(item) or item["url"] in seen:
                continue
            seen.add(item["url"])
            out.append(item)
    if not out:
        for topic in allowed:
            for item in VIDEO_RECS.get(topic, []):
                if not ok(item) or item["url"] in seen:
                    continue
                seen.add(item["url"])
                out.append(item)
    return out[:4]


def _save_checkup_row(
    db: Session,
    *,
    user_id: str,
    score: float,
    weak_topics: list[str],
    summary: str,
    breakdown: dict,
) -> ProgressCheckup:
    today = today_istanbul()
    existing = db.scalars(
        select(ProgressCheckup)
        .where(ProgressCheckup.user_id == user_id)
        .where(ProgressCheckup.checkup_date == today)
    ).first()
    payload_weak = json.dumps(weak_topics, ensure_ascii=False)
    payload_break = json.dumps(breakdown, ensure_ascii=False)
    if existing:
        existing.score = score
        existing.weak_topics = payload_weak
        existing.improvement_summary = summary
        existing.topic_breakdown = payload_break
        row = existing
    else:
        row = ProgressCheckup(
            user_id=user_id,
            checkup_date=today,
            score=score,
            weak_topics=payload_weak,
            improvement_summary=summary,
            topic_breakdown=payload_break,
        )
        db.add(row)
    return row


def submit_baseline(
    db: Session,
    user_id: str,
    answers: list[dict],
    ip_hash: str = "",
) -> dict:
    graded = grade(answers)
    if graded["total"] < 1:
        raise ValueError("Cevap bulunamadı.")
    title = address_for(db, user_id)
    from app.services.exams import exam_of

    exam_target = exam_of(db, user_id)
    try:
        analysis = llm_baseline(graded, title, exam_target)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Teşhis özeti yerelde üretildi: %s", exc)
        analysis = fallback_summary(graded, checkup=False, previous=None, title=title)
    user = get_or_create_user(db, user_id)
    user.is_tested = True
    user.baseline_score = float(graded["score"])
    if not float(getattr(user, "target_score", 0) or 0):
        suggested = float(analysis.get("target_score") or 85)
        user.target_score = min(max(suggested, 1), 100)
    test = DiagnosticTest(
        user_id=user_id,
        answers_json=json.dumps(graded["answers"], ensure_ascii=False),
        score=graded["score"],
        weak_topics=json.dumps(analysis["weak_topics"], ensure_ascii=False),
        strong_topics=json.dumps(analysis["strong_topics"], ensure_ascii=False),
        analysis_summary=analysis["summary"],
        net_range=analysis["net_range"],
    )
    db.add(test)
    baseline = get_baseline(db, user_id)
    if baseline is None:
        baseline = UserBaseline(user_id=user_id)
        db.add(baseline)
    baseline.score = graded["score"]
    baseline.weak_topics = json.dumps(analysis["weak_topics"], ensure_ascii=False)
    baseline.strong_topics = json.dumps(analysis["strong_topics"], ensure_ascii=False)
    baseline.analysis_summary = analysis["summary"]
    baseline.net_range = analysis["net_range"]
    baseline.topic_breakdown = json.dumps(graded["topic_breakdown"], ensure_ascii=False)
    _save_checkup_row(
        db,
        user_id=user_id,
        score=graded["score"],
        weak_topics=analysis["weak_topics"],
        summary=analysis["summary"],
        breakdown=graded["topic_breakdown"],
    )
    mark_diagnostic_ip(db, ip_hash, user_id)
    db.commit()
    db.refresh(baseline)
    return {
        "is_tested": True,
        "score": graded["score"],
        "correct_count": graded["correct_count"],
        "total": graded["total"],
        "weak_topics": analysis["weak_topics"],
        "strong_topics": analysis["strong_topics"],
        "analysis_summary": analysis["summary"],
        "net_range": analysis["net_range"],
        "topic_breakdown": graded["topic_breakdown"],
        "recommended_videos": recommended_videos(analysis["weak_topics"], exam_target),
    }


def submit_checkup(db: Session, user_id: str, answers: list[dict]) -> dict:
    user = get_or_create_user(db, user_id)
    if not user.is_tested:
        raise ValueError("Önce seviye teşhisini bitir.")
    graded = grade(answers)
    if graded["total"] < 1:
        raise ValueError("Cevap bulunamadı.")
    previous = last_checkup(db, user_id)
    prev_payload = None
    if previous:
        prev_payload = {
            "score": float(previous.score or 0),
            "weak_topics": _loads(previous.weak_topics, []),
        }
    from app.services.exams import exam_of

    analysis = llm_checkup(
        graded, prev_payload, address_for(db, user_id), exam_of(db, user_id)
    )
    user.baseline_score = float(graded["score"])
    baseline = get_baseline(db, user_id)
    if baseline:
        baseline.score = graded["score"]
        baseline.weak_topics = json.dumps(analysis["weak_topics"], ensure_ascii=False)
        baseline.analysis_summary = analysis["improvement_summary"]
        baseline.topic_breakdown = json.dumps(graded["topic_breakdown"], ensure_ascii=False)
        baseline.net_range = net_range_for(graded["score"])
    row = _save_checkup_row(
        db,
        user_id=user_id,
        score=graded["score"],
        weak_topics=analysis["weak_topics"],
        summary=analysis["improvement_summary"],
        breakdown=graded["topic_breakdown"],
    )
    db.commit()
    db.refresh(row)
    delta = None
    if prev_payload:
        delta = round(graded["score"] - float(prev_payload["score"]), 1)
    return {
        "score": graded["score"],
        "correct_count": graded["correct_count"],
        "total": graded["total"],
        "weak_topics": analysis["weak_topics"],
        "improvement_summary": analysis["improvement_summary"],
        "score_delta": delta,
        "previous_score": prev_payload["score"] if prev_payload else None,
        "checkup_date": row.checkup_date.isoformat(),
        "topic_breakdown": graded["topic_breakdown"],
        "recommended_videos": recommended_videos(
            analysis["weak_topics"], exam_of(db, user_id)
        ),
    }


def progress_history(db: Session, user_id: str) -> dict:
    rows = list(
        db.scalars(
            select(ProgressCheckup)
            .where(ProgressCheckup.user_id == user_id)
            .order_by(ProgressCheckup.checkup_date.asc(), ProgressCheckup.id.asc())
        ).all()
    )
    points = [
        {
            "date": row.checkup_date.isoformat(),
            "score": float(row.score or 0),
            "weak_topics": _loads(row.weak_topics, []),
            "improvement_summary": row.improvement_summary,
        }
        for row in rows
    ]
    return {"user_id": user_id, "points": points}
