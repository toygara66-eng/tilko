"""Hedef sınav katalogu ve AI kişiselleştirme bloğu."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

DEFAULT_EXAM = "kpss_lisans"
DEFAULT_TARGET_SCORE = 85.0
ISTANBUL_OFFSET = timezone(timedelta(hours=3))
CLOCK_KEY = "_today"
MONTHS_TR = (
    "",
    "Ocak",
    "Şubat",
    "Mart",
    "Nisan",
    "Mayıs",
    "Haziran",
    "Temmuz",
    "Ağustos",
    "Eylül",
    "Ekim",
    "Kasım",
    "Aralık",
)
WEEKDAYS_TR = (
    "Pazartesi",
    "Salı",
    "Çarşamba",
    "Perşembe",
    "Cuma",
    "Cumartesi",
    "Pazar",
)

EXAMS: dict[str, dict[str, str]] = {
    "kpss_lisans": {
        "label": "KPSS Lisans",
        "family": "kpss",
        "board": "ÖSYM",
        "blurb": "GY-GK, 5 şık, ÖSYM KPSS üslubu.",
        "exam_date": "2026-09-06",
        "style": (
            "HEDEF SINAV: KPSS Lisans (Genel Yetenek / Genel Kültür). Kurum: ÖSYM. "
            "Soru 5 şıklı (A-E). Vatandaşlık, tarih, coğrafya, güncel, Türkçe. "
            "Çeldirici klasik ÖSYM kaydırmasıdır (yıl, ferman, organ yetkisi). "
            "KPSS dışı müfredat (lise TYT fizik vb.) uydurma."
        ),
    },
    "kpss_onlisans": {
        "label": "KPSS Önlisans",
        "family": "kpss",
        "board": "ÖSYM",
        "blurb": "Önlisans GY-GK, 5 şık.",
        "exam_date": "2026-09-13",
        "style": (
            "HEDEF SINAV: KPSS Önlisans. Kurum: ÖSYM. 5 şık. "
            "Lisans kadar derin mevzuat yorumu yok; tanım, yıl, organ, temel vatandaşlık. "
            "Çeldirici sade tut, aşırı akademik alan bilgisi ekleme."
        ),
    },
    "kpss_ortaogretim": {
        "label": "KPSS Ortaöğretim",
        "family": "kpss",
        "board": "ÖSYM",
        "blurb": "Ortaöğretim GY-GK, 5 şık.",
        "exam_date": "2026-09-13",
        "style": (
            "HEDEF SINAV: KPSS Ortaöğretim. Kurum: ÖSYM. 5 şık. "
            "Dil sade, bilgi doğrudan. Uzun içtihat / lisans ezberi yok. "
            "Tuzak: yakın yıl ve benzer kurum adları."
        ),
    },
    "yks": {
        "label": "YKS (TYT/AYT)",
        "family": "yks",
        "board": "ÖSYM",
        "blurb": "Üniversite — TYT/AYT.",
        "exam_date": "2027-06-20",
        "style": (
            "HEDEF SINAV: YKS (TYT ve AYT). Kurum: ÖSYM. 5 şık. "
            "MEB lise müfredatı: Türkçe, matematik, fen, sosyal. "
            "KPSS vatandaşlık / kamu personeli ezberi uydurma. "
            "Çeldirici: karışan formül, dönem, yazar, kavram çifti."
        ),
    },
    "oabt": {
        "label": "ÖABT / Alan",
        "family": "oabt",
        "board": "ÖSYM",
        "blurb": "Öğretmenlik alan bilgisi.",
        "exam_date": "2026-09-20",
        "style": (
            "HEDEF SINAV: ÖABT (alan bilgisi + öğretmenlik meslek bilgisi). Kurum: ÖSYM. 5 şık. "
            "Alan kavramı, müfredat, ölçme-değerlendirme, öğrenme kuramı. "
            "Genel KPSS GY-GK ezberi yetmez; alan tuzağını kur."
        ),
    },
    "lgs": {
        "label": "LGS",
        "family": "lgs",
        "board": "MEB",
        "blurb": "Liselere geçiş.",
        "exam_date": "2027-06-14",
        "style": (
            "HEDEF SINAV: LGS (8. sınıf). Kurum: MEB. Şıklar A-E tutarlı olsun. "
            "Ortaokul müfredatı: Türkçe, matematik, fen, T.C. inkılap, din, İngilizce. "
            "Üniversite veya KPSS mevzuatı uydurma. Dil sade, tuzak somut."
        ),
    },
    "other": {
        "label": "Diğer sınavlar",
        "family": "other",
        "board": "ÖSYM",
        "blurb": "Genel ÖSYM tarzı.",
        "exam_date": "2026-09-06",
        "style": (
            "HEDEF SINAV: genel ÖSYM tarzı çoktan seçmeli. 5 şık. "
            "Altyazıdaki derse sadık kal; kurum ve yıl uydurma. "
            "Çeldirici yakın kavram olsun."
        ),
    },
}

ALIASES = {
    "kpss": "kpss_lisans",
    "kpss-lisans": "kpss_lisans",
    "onlisans": "kpss_onlisans",
    "önlisans": "kpss_onlisans",
    "ortaogretim": "kpss_ortaogretim",
    "ortaöğretim": "kpss_ortaogretim",
    "tyt": "yks",
    "ayt": "yks",
    "universite": "yks",
    "üniversite": "yks",
    "öabt": "oabt",
    "alan": "oabt",
    "diger": "other",
    "diğer": "other",
}


def normalize(code: str | None) -> str:
    raw = (code or "").strip().lower().replace("-", "_").replace(" ", "_")
    raw = ALIASES.get(raw, raw)
    if raw in EXAMS:
        return raw
    return DEFAULT_EXAM


def parse_choice(code: str | None) -> str:
    raw = (code or "").strip().lower().replace("-", "_").replace(" ", "_")
    raw = ALIASES.get(raw, raw)
    if raw in EXAMS:
        return raw
    raise ValueError("Geçerli bir sınav hedefi seç: KPSS, YKS, ÖABT veya diğer.")


def meta(code: str | None) -> dict[str, str]:
    return EXAMS[normalize(code)]


def label_for(code: str | None) -> str:
    return meta(code)["label"]


MODE_HINTS: dict[str, str] = {
    "kpss_lisans": (
        "KPSS Lisans: mevzuat, organ yetkisi, yıl/ferman, GY-GK. "
        "TYT/AYT fizik-mat pratik çözüm veya lise fen öncülü uydurma."
    ),
    "kpss_onlisans": (
        "KPSS Önlisans: tanım, yıl, organ, temel vatandaşlık. "
        "Lisans içtihadı ve YKS fen kalıbı yok."
    ),
    "kpss_ortaogretim": (
        "KPSS Ortaöğretim: sade dil, doğrudan bilgi. "
        "Üniversite AYT veya ağır mevzuat yorumu yok."
    ),
    "yks": (
        "YKS (TYT/AYT): TYT'de pratik/hızlı çözüm ve formül kısayolu; "
        "AYT'de kavram derinliği. KPSS vatandaşlık/mevzuat ezberi yok."
    ),
    "oabt": (
        "ÖABT: alan bilgisi, ölçme-değerlendirme, öğrenme kuramı. "
        "Genel KPSS GY-GK yetmez."
    ),
    "lgs": (
        "LGS: ortaokul müfredatı, sade dil, somut tuzak. "
        "Üniversite veya KPSS mevzuatı yok."
    ),
    "other": "Genel ÖSYM çoktan seçmeli; altyazıdaki derse sadık kal.",
}


def dative_label(label: str) -> str:
    """YKS'ye / KPSS Lisans'a — ünlü uyumu + kısaltma."""
    text = (label or "Sınav").strip()
    core = text.split("(")[0].strip() or text
    compact = core.replace(" ", "")
    if compact.isupper() or not any(ch in "aeıioöuüAEIİOÖUÜ" for ch in core):
        return f"{core}'ye"
    vowels = [ch for ch in core.lower() if ch in "aeıioöuü"]
    vowel = vowels[-1] if vowels else "e"
    use_e = vowel in "eiöü"
    last = core[-1:].lower()
    if last in "aeıioöuü":
        ending = "'ye" if use_e else "'ya"
    else:
        ending = "'e" if use_e else "'a"
    return f"{core}{ending}"


def exam_mode_block(code: str | None) -> str:
    target = normalize(code)
    info = meta(target)
    hint = MODE_HINTS.get(target) or MODE_HINTS.get(info["family"], "")
    return (
        f"[EXAM_MODE]: {target}\n"
        f"Hedef sınav etiketi: {info['label']}. {hint}"
    )


def prompt_block(code: str | None) -> str:
    info = meta(code)
    return (
        f"{exam_mode_block(code)}\n"
        f"{info['style']}\n"
        "Not, soru, koç ve tuzak analizini BU sınavın üslubuna göre yaz. "
        "Başka sınavın kalıplarını karıştırma."
    )


def matches_exam(item: dict, exam_target: str | None) -> bool:
    """Soru kaydının exams etiketini kullanıcının hedefine göre süz."""
    target = normalize(exam_target)
    family = family_of(target)
    raw = item.get("exams")
    if not raw:
        return family == "kpss"
    tags = {str(tag).strip().lower().replace("-", "_") for tag in raw if str(tag).strip()}
    expanded: set[str] = set()
    for tag in tags:
        if tag == "kpss":
            expanded.update({"kpss", "kpss_lisans", "kpss_onlisans", "kpss_ortaogretim"})
        else:
            expanded.add(ALIASES.get(tag, tag))
            expanded.add(tag)
    return target in expanded or family in expanded


def countdown(code: str | None, today: date | None = None, db: Session | None = None) -> dict:
    target = normalize(code)
    stamp = scheduled_exam_date(target, db)
    now = effective_today(db, today)
    days = get_days_remaining(target, db, now)
    label = label_for(target)
    headed = dative_label(label)
    if days > 1:
        headline = f"{headed} {days} Gün Kaldı"
    elif days == 1:
        headline = f"{headed} 1 Gün Kaldı"
    elif days == 0:
        headline = f"{label} bugün"
    else:
        headline = f"{label} geride kaldı"
    return {
        "exam_target": target,
        "exam_label": label,
        "exam_date": stamp.isoformat(),
        "exam_date_label": format_date_tr(stamp),
        "today": now.isoformat(),
        "today_label": format_date_tr(now),
        "days_left": days,
        "headline": headline,
    }


def exam_of(db: Session, user_id: str | None) -> str:
    if not user_id:
        return DEFAULT_EXAM
    from app.database.models import User

    row = db.get(User, user_id)
    stored = getattr(row, "exam_target", "") if row is not None else ""
    if not stored:
        return DEFAULT_EXAM
    return normalize(stored)


def set_exam_target(db: Session, user_id: str, exam_target: str) -> dict:
    from app.services.penalty import get_or_create_user
    from app.services.ranks import address_for

    uid = (user_id or "").strip()
    if not uid:
        raise ValueError("Kullanıcı kimliği gerekli.")
    code = parse_choice(exam_target)
    user = get_or_create_user(db, uid)
    previous = normalize(getattr(user, "exam_target", "") or "") if (user.exam_target or "").strip() else ""
    changed = bool(previous) and previous != code
    user.exam_target = code
    user.is_onboarded = True
    reset = {"reset": False, "is_tested": bool(user.is_tested)}
    if changed or not previous:
        reset = reset_exam_scope(db, uid, code, previous, commit=False)
    db.commit()
    title = address_for(db, uid)
    clock = countdown(code, db=db)
    first = not previous
    if changed:
        message = (
            f"Hedef {label_for(code)} olarak değişti {title}. "
            "Soru havuzu, deneme ve koç bu sınava göre sıfırlandı."
        )
    elif first:
        message = f"Hedef belirlendi {title}, rota senin sınavına göre çizildi!"
    else:
        message = f"Hedef zaten {label_for(code)}, {title}."
    return {
        "user_id": uid,
        "exam_target": code,
        "exam_label": label_for(code),
        "is_onboarded": True,
        "is_tested": bool(reset.get("is_tested", user.is_tested)),
        "reset": bool(reset.get("reset")),
        "title": title,
        "message": message,
        **{
            k: clock[k]
            for k in ("days_left", "headline", "exam_date", "exam_date_label", "today", "today_label")
        },
    }


def reset_exam_scope(
    db: Session,
    user_id: str,
    new_code: str,
    previous: str = "",
    *,
    commit: bool = True,
) -> dict:
    """Hedef değişince teşhis, deneme ve önerileri yeni sınava çevir."""
    from sqlalchemy import select

    from app.database.models import DynamicExam, User, UserBaseline

    uid = (user_id or "").strip()
    switched = bool(previous) and previous != new_code
    user = db.get(User, uid)
    if user is None:
        return {"reset": False, "is_tested": False}
    if switched:
        user.is_tested = False
        user.baseline_score = 0.0
        baseline = db.get(UserBaseline, uid)
        if baseline is not None:
            baseline.score = 0.0
            baseline.weak_topics = "[]"
            baseline.strong_topics = "[]"
            baseline.analysis_summary = ""
            baseline.net_range = ""
            baseline.topic_breakdown = "{}"
            db.add(baseline)
        pending = db.scalars(
            select(DynamicExam).where(
                DynamicExam.user_id == uid,
                DynamicExam.status == "pending",
            )
        ).all()
        for row in pending:
            if (row.exam_target or "") != new_code:
                row.status = "abandoned"
                db.add(row)
        db.add(user)
    if commit:
        db.commit()
    return {
        "reset": switched,
        "is_tested": bool(user.is_tested),
    }


def format_date_tr(day: date | None) -> str:
    if day is None:
        return ""
    return f"{day.day} {MONTHS_TR[day.month]} {day.year} {WEEKDAYS_TR[day.weekday()]}"


def today_istanbul() -> date:
    try:
        return datetime.now(ZoneInfo("Europe/Istanbul")).date()
    except ZoneInfoNotFoundError:
        return datetime.now(ISTANBUL_OFFSET).date()


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _store_exam_datetime(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, 10, 0, tzinfo=ISTANBUL_OFFSET)


def _parse_admin_date(raw: str | datetime | date) -> date:
    if isinstance(raw, datetime):
        stamp = _aware(raw) or raw
        try:
            return stamp.astimezone(ISTANBUL_OFFSET).date()
        except Exception:  # noqa: BLE001
            return stamp.date()
    if isinstance(raw, date):
        return raw
    text = (raw or "").strip().replace("Z", "+00:00")
    if not text:
        raise ValueError("Sınav tarihi gerekli.")
    try:
        if "T" in text:
            parsed = datetime.fromisoformat(text)
            parsed = _aware(parsed) or parsed
            return parsed.astimezone(ISTANBUL_OFFSET).date() if parsed.tzinfo else parsed.date()
        return date.fromisoformat(text[:10])
    except ValueError as exc:
        raise ValueError("Tarih YYYY-AA-GG formatında olmalı.") from exc


def seed_exam_schedules(db: Session) -> None:
    """Boş takvimi katalog varsayılanlarıyla doldurur; mevcut satıra dokunmaz."""
    from app.database.models import ExamSchedule

    dirty = False
    for code, info in EXAMS.items():
        if code.startswith("_"):
            continue
        if db.get(ExamSchedule, code) is not None:
            continue
        raw = (info.get("exam_date") or "2026-09-06")[:10]
        try:
            day = date.fromisoformat(raw)
        except ValueError:
            day = date(2026, 9, 6)
        db.add(ExamSchedule(exam_target=code, exam_date=_store_exam_datetime(day)))
        dirty = True
    if dirty:
        db.commit()


def scheduled_exam_date(exam_target: str | None, db: Session | None = None) -> date:
    """ExamSchedule tablosundaki resmi sınav günü."""
    from app.database.models import ExamSchedule
    from app.database.session import SessionLocal

    target = normalize(exam_target)
    own = db is None
    session = db if db is not None else SessionLocal()
    try:
        seed_exam_schedules(session)
        row = session.get(ExamSchedule, target)
        if row is not None and row.exam_date is not None:
            stamp = _aware(row.exam_date)
            if stamp is None:
                return today_istanbul()
            try:
                return stamp.astimezone(ISTANBUL_OFFSET).date()
            except Exception:  # noqa: BLE001
                return stamp.date()
        raw = (meta(target).get("exam_date") or "2026-09-06")[:10]
        try:
            return date.fromisoformat(raw)
        except ValueError:
            return today_istanbul()
    finally:
        if own:
            session.close()


def effective_today(db: Session | None = None, today: date | None = None) -> date:
    if today is not None:
        return today
    from app.database.models import ExamSchedule
    from app.database.session import SessionLocal

    own = db is None
    session = db if db is not None else SessionLocal()
    try:
        row = session.get(ExamSchedule, CLOCK_KEY)
        if row is not None and row.exam_date is not None:
            stamp = _aware(row.exam_date)
            if stamp is None:
                return today_istanbul()
            try:
                return stamp.astimezone(ISTANBUL_OFFSET).date()
            except Exception:  # noqa: BLE001
                return stamp.date()
        return today_istanbul()
    finally:
        if own:
            session.close()


def clock_is_override(db: Session | None = None) -> bool:
    from app.database.models import ExamSchedule
    from app.database.session import SessionLocal

    own = db is None
    session = db if db is not None else SessionLocal()
    try:
        row = session.get(ExamSchedule, CLOCK_KEY)
        return row is not None and row.exam_date is not None
    finally:
        if own:
            session.close()


def get_days_remaining(
    exam_target: str | None,
    db: Session | None = None,
    today: date | None = None,
) -> int:
    """Hesap günü ile ExamSchedule.exam_date arasındaki gün farkı. Sabit 365 hesabı yok."""
    now = effective_today(db, today)
    return (scheduled_exam_date(exam_target, db) - now).days


def exam_date_for(code: str | None, today: date | None = None, db: Session | None = None) -> date:
    return scheduled_exam_date(code, db)


def days_until_exam(code: str | None, today: date | None = None, db: Session | None = None) -> int:
    return get_days_remaining(code, db=db, today=today)


CALENDAR_ORDER = (
    "yks",
    "kpss_lisans",
    "kpss_onlisans",
    "kpss_ortaogretim",
    "lgs",
    "oabt",
)


def list_exam_schedules(db: Session, today: date | None = None) -> dict:
    seed_exam_schedules(db)
    now = effective_today(db, today)
    exams = []
    for code in CALENDAR_ORDER:
        if code not in EXAMS:
            continue
        day = scheduled_exam_date(code, db)
        exams.append(
            {
                "exam_target": code,
                "label": label_for(code),
                "exam_date": day.isoformat(),
                "exam_date_label": format_date_tr(day),
                "days_remaining": get_days_remaining(code, db, now),
            }
        )
    return {
        "today": now.isoformat(),
        "today_label": format_date_tr(now),
        "today_override": clock_is_override(db) if today is None else True,
        "real_today": today_istanbul().isoformat(),
        "real_today_label": format_date_tr(today_istanbul()),
        "exams": exams,
        "count": len(exams),
    }


def update_clock_today(db: Session, exam_date: str | None = None, reset: bool = False) -> dict:
    from app.database.models import ExamSchedule

    row = db.get(ExamSchedule, CLOCK_KEY)
    if reset or not (exam_date or "").strip():
        if row is not None:
            db.delete(row)
            db.commit()
        now = today_istanbul()
        return {
            **list_exam_schedules(db),
            "message": f"Hesap günü gerçek bugüne alındı: {format_date_tr(now)}.",
        }
    day = _parse_admin_date(exam_date or "")
    if day == today_istanbul():
        if row is not None:
            db.delete(row)
            db.commit()
        return {
            **list_exam_schedules(db),
            "message": f"Hesap günü gerçek bugün: {format_date_tr(day)}.",
        }
    stamp = _store_exam_datetime(day)
    if row is None:
        row = ExamSchedule(exam_target=CLOCK_KEY, exam_date=stamp)
    else:
        row.exam_date = stamp
    db.add(row)
    db.commit()
    return {
        **list_exam_schedules(db),
        "message": f"Hesap günü {format_date_tr(day)} olarak ayarlandı. Kalan günler buna göre.",
    }


def update_exam_schedule(db: Session, exam_target: str, exam_date: str | date | datetime) -> dict:
    from app.database.models import ExamSchedule

    code = parse_choice(exam_target)
    day = _parse_admin_date(exam_date)
    seed_exam_schedules(db)
    row = db.get(ExamSchedule, code)
    if row is None:
        row = ExamSchedule(exam_target=code, exam_date=_store_exam_datetime(day))
    else:
        row.exam_date = _store_exam_datetime(day)
    db.add(row)
    db.commit()
    db.refresh(row)
    remaining = get_days_remaining(code, db)
    return {
        "ok": True,
        "exam_target": code,
        "label": label_for(code),
        "exam_date": scheduled_exam_date(code, db).isoformat(),
        "exam_date_label": format_date_tr(scheduled_exam_date(code, db)),
        "days_remaining": remaining,
        "message": (
            f"{label_for(code)} tarihi {format_date_tr(day)} olarak güncellendi. "
            f"Kalan: {remaining} gün."
        ),
    }


def family_of(code: str | None) -> str:
    return meta(code)["family"]


SUBJECTS_BY_FAMILY: dict[str, list[str]] = {
    "kpss": ["Türkçe", "Matematik", "Tarih", "Coğrafya", "Vatandaşlık", "Güncel"],
    "yks": ["Türkçe", "Matematik", "Fizik", "Kimya", "Biyoloji", "Tarih", "Coğrafya"],
    "oabt": ["Alan bilgisi", "Ölçme-değerlendirme", "Öğrenme kuramı"],
    "lgs": ["Türkçe", "Matematik", "Fen", "İnkılap"],
    "other": ["Türkçe", "Matematik", "Genel kültür"],
}

QUESTION_COUNT_OPTIONS = (10, 15, 20, 25)
SECONDS_PER_QUESTION = 75


def subjects_for(code: str | None) -> list[str]:
    family = family_of(code)
    return list(SUBJECTS_BY_FAMILY.get(family) or SUBJECTS_BY_FAMILY["kpss"])


def catalog_for(code: str | None) -> dict:
    target = normalize(code)
    return {
        "exam_target": target,
        "exam_label": label_for(target),
        "family": family_of(target),
        "subjects": subjects_for(target),
        "question_counts": list(QUESTION_COUNT_OPTIONS),
        "seconds_per_question": SECONDS_PER_QUESTION,
    }


def set_target_score(db: Session, user_id: str, target_score: float) -> dict:
    from app.services.penalty import get_or_create_user
    from app.services.ranks import address_for

    uid = (user_id or "").strip()
    if not uid:
        raise ValueError("Kullanıcı kimliği gerekli.")
    try:
        score = float(target_score)
    except (TypeError, ValueError) as exc:
        raise ValueError("Hedef puan 1 ile 100 arasında olmalı.") from exc
    if score < 1 or score > 100:
        raise ValueError("Hedef puan 1 ile 100 arasında olmalı.")
    user = get_or_create_user(db, uid)
    user.target_score = round(score, 1)
    db.commit()
    title = address_for(db, uid)
    return {
        "user_id": uid,
        "target_score": user.target_score,
        "title": title,
        "message": f"Hedef {user.target_score:.0f} puan, {title}. Çubuk buna göre çizildi.",
    }
