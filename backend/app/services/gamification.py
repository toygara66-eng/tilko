import hashlib
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import UserBadge, UserStats
from app.services.ranks import address_for, fox_rank
from app.services.traps import due_traps

XP_PER_CLEAR = 25
XP_STREAK_BONUS = 25
XP_PER_LEVEL = 80
XP_HUNT_CORRECT = 50
XP_POMODORO = 30
XP_DYNAMIC_PER_CORRECT = 8
XP_DYNAMIC_CAP = 120

UNLOCKS = (
    {"id": "defter", "min_level": 1, "title": "Tuzak Defteri"},
    {"id": "gorevler", "min_level": 1, "title": "Günlük Görevler"},
    {"id": "bulten", "min_level": 2, "title": "Haftanın Tuzakları"},
    {"id": "liderlik", "min_level": 3, "title": "Liderlik Tablosu"},
    {"id": "usta", "min_level": 6, "title": "Usta Avcı Alanı"},
)

BADGE_CATALOG = {
    "ilk_tuzak": {"title": "İlk Düşüş", "hint": "Deftere ilk tuzağı yazdın"},
    "ilk_temizlik": {"title": "İlk Temizlik", "hint": "Bir tuzağı doğru çözdün"},
    "seri_3": {"title": "3 Gün Seri", "hint": "Üç gün üst üste defteri temizledin"},
    "seri_7": {"title": "Haftalık Ateş", "hint": "Yedi gün seri"},
    "seri_15": {"title": "Demir İrade", "hint": "On beş gün seri"},
    "avci_10": {"title": "Tuzak Avcısı", "hint": "10 tuzak temizlendi"},
    "avci_50": {"title": "Usta Avcı", "hint": "50 tuzak temizlendi"},
    "dakik": {"title": "Dakik Aday", "hint": "Süre tuzağına düşmeden 5 temizlik"},
}


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _level_for(xp: int) -> int:
    return 1 + max(xp, 0) // XP_PER_LEVEL


def alias_for(user_id: str) -> str:
    digest = hashlib.sha1(user_id.encode("utf-8")).hexdigest()[:4].upper()
    return f"Aday-{digest}"


def _get_or_create(db: Session, user_id: str) -> UserStats:
    row = db.get(UserStats, user_id)
    if row is None:
        row = UserStats(user_id=user_id, display_name=alias_for(user_id), level=1)
        db.add(row)
        db.flush()
    if not row.display_name:
        row.display_name = alias_for(user_id)
    return row


def _award(db: Session, user_id: str, badge_id: str) -> str | None:
    exists = db.scalars(
        select(UserBadge).where(UserBadge.user_id == user_id).where(UserBadge.badge_id == badge_id)
    ).first()
    if exists:
        return None
    db.add(UserBadge(user_id=user_id, badge_id=badge_id))
    return badge_id


def badges_for(db: Session, user_id: str) -> list[dict]:
    rows = db.scalars(select(UserBadge).where(UserBadge.user_id == user_id)).all()
    out = []
    for row in rows:
        meta = BADGE_CATALOG.get(row.badge_id, {"title": row.badge_id, "hint": ""})
        out.append(
            {
                "id": row.badge_id,
                "title": meta["title"],
                "hint": meta["hint"],
                "earned_at": row.earned_at.isoformat() if row.earned_at else None,
            }
        )
    return out


def unlocked_for(level: int) -> list[dict]:
    return [
        {**item, "unlocked": level >= item["min_level"]}
        for item in UNLOCKS
    ]


def public_progress(db: Session, user_id: str, ip_hash: str = "") -> dict:
    from app.services import prizes as prize_service
    from app.services import credits as credit_service

    row = _get_or_create(db, user_id)
    prize_payload = prize_service.profile_prize(db, user_id)
    credit_view = credit_service.snapshot(db, user_id)
    from app.services import diagnostic as diagnostic_service

    diag = diagnostic_service.status(db, user_id, ip_hash=ip_hash)
    db.commit()
    rank = fox_rank(row.xp)
    from app.services.exams import (
        DEFAULT_TARGET_SCORE,
        countdown,
        exam_of,
        label_for,
    )
    from app.services.penalty import get_or_create_user

    user = get_or_create_user(db, user_id)
    stored = (user.exam_target or "").strip()
    is_onboarded = bool(user.is_onboarded)
    exam_code = stored if stored else ""
    exam_label = label_for(stored) if stored else ""
    exam_for_date = stored or exam_of(db, user_id)
    clock = countdown(exam_for_date, db=db)
    current_score = float(diag["baseline_score"] or 0)
    raw_target = float(getattr(user, "target_score", 0) or 0)
    target_score = raw_target if raw_target >= 1 else DEFAULT_TARGET_SCORE
    target_is_set = raw_target >= 1
    if target_score > 0:
        progress_pct = int(round(100 * min(max(current_score, 0) / target_score, 1)))
    else:
        progress_pct = 0
    from app.services.teacher import dashboard_for, display_name_of, normalize_role

    role = normalize_role(getattr(user, "role", "") or "student")
    teacher_id = (getattr(user, "teacher_id", "") or "").strip()
    shown = (getattr(user, "display_name", "") or "").strip() or row.display_name
    return {
        "user_id": user_id,
        "display_name": shown,
        "xp": row.xp,
        "level": row.level,
        "title": rank["title"],
        "title_emoji": rank["emoji"],
        "xp_to_next": XP_PER_LEVEL - (row.xp % XP_PER_LEVEL),
        "current_streak": row.current_streak,
        "longest_streak": row.longest_streak,
        "traps_logged": row.traps_logged,
        "traps_cleared": row.traps_cleared,
        "badges": badges_for(db, user_id),
        "unlocks": unlocked_for(row.level),
        "prize": prize_payload,
        **credit_view,
        "is_tested": diag["is_tested"],
        "baseline_score": diag["baseline_score"],
        "checkup_due": diag["checkup_due"],
        "weak_topics": diag["weak_topics"],
        "analysis_summary": (diag.get("baseline") or {}).get("analysis_summary") or "",
        "recommended_videos": diag["recommended_videos"],
        "exam_target": exam_code,
        "exam_label": exam_label,
        "is_onboarded": is_onboarded,
        "target_score": target_score,
        "target_is_set": target_is_set,
        "current_score": current_score,
        "progress_pct": progress_pct,
        "days_until_exam": clock["days_left"],
        "exam_date": clock["exam_date"],
        "exam_date_label": clock.get("exam_date_label") or "",
        "today": clock.get("today") or "",
        "today_label": clock.get("today_label") or "",
        "countdown_headline": clock["headline"],
        "role": role,
        "teacher_id": teacher_id,
        "teacher_name": display_name_of(db, teacher_id) if teacher_id else "",
        "dashboard": dashboard_for(role),
    }


def grant_xp(db: Session, user_id: str, amount: int) -> dict:
    row = _get_or_create(db, user_id)
    gained = max(int(amount or 0), 0)
    row.xp += gained
    row.level = _level_for(row.xp)
    db.commit()
    rank = fox_rank(row.xp)
    return {
        "xp_gained": gained,
        "xp": row.xp,
        "level": row.level,
        "title": rank["title"],
        "title_emoji": rank["emoji"],
    }


def award_dynamic_exam(db: Session, user_id: str, *, correct_count: int, already: bool) -> dict:
    if already:
        row = _get_or_create(db, user_id)
        rank = fox_rank(row.xp)
        return {
            "xp_gained": 0,
            "xp": row.xp,
            "level": row.level,
            "title": rank["title"],
            "title_emoji": rank["emoji"],
        }
    gained = min(max(int(correct_count or 0), 0) * XP_DYNAMIC_PER_CORRECT, XP_DYNAMIC_CAP)
    return grant_xp(db, user_id, gained)


def award_hunt(db: Session, user_id: str, *, correct: bool, already: bool) -> dict:
    if already or not correct:
        row = _get_or_create(db, user_id)
        rank = fox_rank(row.xp)
        return {
            "xp_gained": 0,
            "xp": row.xp,
            "level": row.level,
            "title": rank["title"],
            "title_emoji": rank["emoji"],
        }
    return grant_xp(db, user_id, XP_HUNT_CORRECT)


def complete_pomodoro(db: Session, user_id: str, session_id: str) -> dict:
    token = (session_id or "").strip()[:64]
    row = _get_or_create(db, user_id)
    if token and row.last_pomodoro_session == token:
        rank = fox_rank(row.xp)
        return {
            "xp_gained": 0,
            "xp": row.xp,
            "level": row.level,
            "title": rank["title"],
            "title_emoji": rank["emoji"],
            "already": True,
        }
    if token:
        row.last_pomodoro_session = token
    result = grant_xp(db, user_id, XP_POMODORO)
    result["already"] = False
    return result


def record_wrong(db: Session, user_id: str) -> list[str]:
    row = _get_or_create(db, user_id)
    row.traps_logged += 1
    earned = []
    badge = _award(db, user_id, "ilk_tuzak")
    if badge:
        earned.append(badge)
    db.commit()
    return earned


def record_clear(
    db: Session,
    user_id: str,
    *,
    correct: bool,
    notebook_cleared: bool,
    time_trap: bool,
) -> dict:
    row = _get_or_create(db, user_id)
    gained = 0
    earned: list[str] = []
    if not correct:
        db.commit()
        rank = fox_rank(row.xp)
        return {
            "xp_gained": 0,
            "new_badges": [],
            "streak": row.current_streak,
            "level": row.level,
            "title": rank["title"],
            "title_emoji": rank["emoji"],
            "xp": row.xp,
        }

    row.traps_cleared += 1
    gained += XP_PER_CLEAR
    first = _award(db, user_id, "ilk_temizlik")
    if first:
        earned.append(first)
    if row.traps_cleared >= 10:
        badge = _award(db, user_id, "avci_10")
        if badge:
            earned.append(badge)
    if row.traps_cleared >= 50:
        badge = _award(db, user_id, "avci_50")
        if badge:
            earned.append(badge)
    if not time_trap and row.traps_cleared >= 5:
        badge = _award(db, user_id, "dakik")
        if badge:
            earned.append(badge)

    today = _today().isoformat()
    if notebook_cleared:
        last = row.last_streak_date or ""
        yesterday = (_today() - timedelta(days=1)).isoformat()
        if last == today:
            pass
        elif last == yesterday:
            row.current_streak += 1
        else:
            row.current_streak = 1
        row.last_streak_date = today
        row.longest_streak = max(row.longest_streak, row.current_streak)
        gained += XP_STREAK_BONUS
        if row.current_streak >= 3:
            badge = _award(db, user_id, "seri_3")
            if badge:
                earned.append(badge)
        if row.current_streak >= 7:
            badge = _award(db, user_id, "seri_7")
            if badge:
                earned.append(badge)
        if row.current_streak >= 15:
            badge = _award(db, user_id, "seri_15")
            if badge:
                earned.append(badge)

    row.xp += gained
    row.level = _level_for(row.xp)
    db.commit()
    rank = fox_rank(row.xp)
    return {
        "xp_gained": gained,
        "new_badges": earned,
        "streak": row.current_streak,
        "level": row.level,
        "notebook_cleared": notebook_cleared,
        "title": rank["title"],
        "title_emoji": rank["emoji"],
        "xp": row.xp,
    }


def after_complete(db: Session, user_id: str, *, correct: bool, time_trap: bool) -> dict:
    remaining = due_traps(db, user_id)
    return record_clear(
        db,
        user_id,
        correct=correct,
        notebook_cleared=correct and not remaining,
        time_trap=time_trap,
    )


def leaderboard(db: Session, limit: int = 20) -> list[dict]:
    rows = list(db.scalars(select(UserStats)).all())

    def score(row: UserStats) -> float:
        denom = max(row.traps_cleared + row.traps_logged, 1)
        efficiency = row.traps_cleared / denom
        return round(row.traps_cleared * efficiency * 100 + row.current_streak * 5, 1)

    ranked = sorted(rows, key=score, reverse=True)[:limit]
    board = []
    for index, row in enumerate(ranked, start=1):
        board.append(
            {
                "rank": index,
                "display_name": row.display_name or alias_for(row.user_id),
                "level": row.level,
                "traps_cleared": row.traps_cleared,
                "traps_logged": row.traps_logged,
                "current_streak": row.current_streak,
                "score": score(row),
            }
        )
    return board
