import random

from sqlalchemy.orm import Session

from app.database.models import TrapNotebook, User
from app.services import traps as trap_service
from app.services.ranks import fill_title, address_for

UNLOCK_STREAK = 3

FALLBACK_TRAPS = [
    {
        "id": -1,
        "user_id": "",
        "question_id": "fallback_tanzimat",
        "question_text": "Tanzimat Fermanı hangi yılda ilan edilmiştir?",
        "options": {
            "A": "1839",
            "B": "1856",
            "C": "1876",
            "D": "1908",
            "E": "1923",
        },
        "correct": "A",
        "chosen": "",
        "explanation": "1839 Gülhane Hatt-ı Hümayunu = Tanzimat. 1856 Islahat’tır.",
        "distractor_analysis": "1856 ve 1876 klasik ÖSYM kaydırması.",
        "teacher_note": "{title}, 1856’ya kaydıysan sazan oldun. Tanzimat 1839 — karıştırma!",
        "topic": "Tarih",
        "time_spent_seconds": 0,
        "time_trap_triggered": False,
        "review_count": 0,
        "next_review_date": None,
    },
    {
        "id": -2,
        "user_id": "",
        "question_id": "fallback_anayasa",
        "question_text": "Türkiye’de yürürlükteki Anayasa hangi yılda kabul edilmiştir?",
        "options": {
            "A": "1921",
            "B": "1924",
            "C": "1961",
            "D": "1982",
            "E": "2017",
        },
        "correct": "D",
        "chosen": "",
        "explanation": "Yürürlükteki metin 1982 Anayasası’dır.",
        "distractor_analysis": "2017 değişiklik yılıdır, kabul yılı değildir.",
        "teacher_note": "2017’ye gittin değil mi? Anayasa 82, değişiklik 17. Deftere yaz, unutma.",
        "topic": "Vatandaşlık",
        "time_spent_seconds": 0,
        "time_trap_triggered": False,
        "review_count": 0,
        "next_review_date": None,
    },
    {
        "id": -3,
        "user_id": "",
        "question_id": "fallback_mesrutiyet",
        "question_text": "Kanun-i Esasi hangi olayla yürürlüğe girmiştir?",
        "options": {
            "A": "Tanzimat",
            "B": "Islahat",
            "C": "I. Meşrutiyet",
            "D": "II. Meşrutiyet",
            "E": "Cumhuriyet",
        },
        "correct": "C",
        "chosen": "",
        "explanation": "1876 I. Meşrutiyet = Kanun-i Esasi. 1908 II. Meşrutiyet’tir.",
        "distractor_analysis": "Yıl ve ferman isimleri karıştırılır.",
        "teacher_note": "1908’e sapıttın. Kanun-i Esasi = I. Meşrutiyet, 1876. Tekrar et.",
        "topic": "Tarih",
        "time_spent_seconds": 0,
        "time_trap_triggered": False,
        "review_count": 0,
        "next_review_date": None,
    },
]


def get_or_create_user(db: Session, user_id: str) -> User:
    uid = (user_id or "").strip()
    if not uid or uid.startswith("aday-"):
        raise ValueError("Devam etmek için kayıt ol veya giriş yap.")
    row = db.get(User, uid)
    if row is None:
        row = User(user_id=uid, is_penalized=False, penalty_clear_count=0)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def apply_penalty(db: Session, user_id: str) -> User:
    row = get_or_create_user(db, user_id)
    row.is_penalized = True
    row.penalty_clear_count = 0
    db.commit()
    db.refresh(row)
    return row


def clear_penalty(db: Session, user_id: str, force: bool = False) -> User:
    row = get_or_create_user(db, user_id)
    if not row.is_penalized:
        return row
    if not force and row.penalty_clear_count < UNLOCK_STREAK:
        raise PermissionError(
            f"Hey {address_for(db, user_id)}, kilit için peş peşe 3 doğru gerekir."
        )
    row.is_penalized = False
    row.penalty_clear_count = 0
    db.commit()
    db.refresh(row)
    return row


def next_question(db: Session, user_id: str, exclude_id: int | None = None) -> dict:
    rows = trap_service.all_traps(db, user_id)
    pool = [trap_service.to_public(row) for row in rows if row.id != exclude_id]
    if pool:
        return random.choice(pool)
    fallback = [item for item in FALLBACK_TRAPS if item["id"] != exclude_id]
    pick = dict(random.choice(fallback or FALLBACK_TRAPS))
    pick["user_id"] = user_id
    pick["teacher_note"] = fill_title(str(pick.get("teacher_note") or ""), address_for(db, user_id))
    return pick


def register_answer(db: Session, user_id: str, trap_id: int, chosen: str) -> dict:
    row = get_or_create_user(db, user_id)
    letter = (chosen or "").strip().upper()[:1]
    notebook_row = None
    if trap_id > 0:
        notebook_row = db.get(TrapNotebook, trap_id)
        if notebook_row is None or notebook_row.user_id != user_id:
            raise KeyError("Tuzak sorusu bulunamadı.")
        correct_letter = (notebook_row.correct or "").strip().upper()[:1]
    else:
        fallback = next((item for item in FALLBACK_TRAPS if item["id"] == trap_id), None)
        if fallback is None:
            raise KeyError("Tuzak sorusu bulunamadı.")
        correct_letter = str(fallback["correct"]).upper()[:1]

    ok = letter == correct_letter
    if ok:
        row.penalty_clear_count = min(row.penalty_clear_count + 1, UNLOCK_STREAK)
    else:
        row.penalty_clear_count = 0

    unlocked = ok and row.penalty_clear_count >= UNLOCK_STREAK
    if unlocked:
        row.is_penalized = False
        row.penalty_clear_count = 0

    db.flush()
    if notebook_row is not None:
        trap_service.complete_trap(db, user_id, trap_id, letter)

    db.commit()
    db.refresh(row)
    return {
        "correct": ok,
        "streak": 0 if unlocked else row.penalty_clear_count,
        "unlocked": unlocked,
        "is_penalized": bool(row.is_penalized),
        "needed": UNLOCK_STREAK,
    }
