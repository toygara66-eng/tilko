"""Aylık Sazan Avı sıralaması ve indirim otomasyonu."""

from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.models import (
    ChallengeLeaderboard,
    DailyChallenge,
    MonthlyPrizeRun,
    User,
    UserStats,
)
from app.services.gamification import alias_for
from app.services.penalty import get_or_create_user
from app.services import anti_cheat

ISTANBUL_OFFSET = timezone(timedelta(hours=3))
SCALE_AT = 10_000
LAUNCH_BANNER = (
    "Kürsü Ödülü: Ay sonunda ilk 3'e girenler sonraki ay BEDAVA Pro kazanıyor!"
)
SCALE_BANNER = (
    "Büyük Ödül: Ay sonunda ilk 3'e bedava Pro, ilk 10'a %50, "
    "ilk 100'e %25 indirim seni bekliyor!"
)


def today_istanbul() -> date:
    try:
        return datetime.now(ZoneInfo("Europe/Istanbul")).date()
    except ZoneInfoNotFoundError:
        return datetime.now(ISTANBUL_OFFSET).date()


def month_key(value: date) -> str:
    return f"{value.year:04d}-{value.month:02d}"


def month_bounds(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    last = monthrange(year, month)[1]
    end = date(year, month, last) + timedelta(days=1)
    return start, end


def parse_month(key: str) -> tuple[int, int]:
    year_s, month_s = key.split("-", 1)
    return int(year_s), int(month_s)


def previous_month_key(today: date | None = None) -> str:
    day = today or today_istanbul()
    if day.month == 1:
        return f"{day.year - 1:04d}-12"
    return f"{day.year:04d}-{day.month - 1:02d}"


def count_active_users(db: Session) -> int:
    accounts = set(db.scalars(select(User.user_id)).all())
    players = set(db.scalars(select(UserStats.user_id)).all())
    return len(accounts | players)


def prize_stage(total_active_users: int) -> str:
    return "scale" if total_active_users >= SCALE_AT else "launch"


def prize_banner(total_active_users: int) -> str:
    if prize_stage(total_active_users) == "scale":
        return SCALE_BANNER
    return LAUNCH_BANNER


def prize_meta(db: Session) -> dict:
    total = count_active_users(db)
    return {
        "total_active_users": total,
        "prize_stage": prize_stage(total),
        "prize_banner": prize_banner(total),
    }


def empty_prize(rank: int | None = None) -> dict:
    return {
        "monthly_rank": rank,
        "is_free_next_month": False,
        "discount_percentage": 0,
        "badge": None,
        "tier": None,
    }


def prize_for_rank(rank: int | None, total_active_users: int = 0) -> dict:
    if not rank or rank < 1:
        return empty_prize(None)
    scaled = prize_stage(total_active_users) == "scale"
    if rank <= 3:
        return {
            "monthly_rank": rank,
            "is_free_next_month": True,
            "discount_percentage": 0,
            "badge": "Bedava Ay 🎟️",
            "tier": "free",
        }
    if not scaled:
        return empty_prize(rank)
    if rank <= 10:
        return {
            "monthly_rank": rank,
            "is_free_next_month": False,
            "discount_percentage": 50,
            "badge": "%50 İndirim Sahibi 🎟️",
            "tier": "50",
        }
    if rank <= 100:
        return {
            "monthly_rank": rank,
            "is_free_next_month": False,
            "discount_percentage": 25,
            "badge": "%25 İndirim Sahibi 🎟️",
            "tier": "25",
        }
    return empty_prize(rank)


def monthly_standings(db: Session, source_month: str, limit: int = 100) -> list[dict]:
    year, month = parse_month(source_month)
    start, end = month_bounds(year, month)
    rows = db.execute(
        select(
            ChallengeLeaderboard.user_id,
            func.count().label("hits"),
            func.avg(ChallengeLeaderboard.time_spent_ms).label("avg_ms"),
        )
        .join(DailyChallenge, DailyChallenge.id == ChallengeLeaderboard.challenge_id)
        .where(ChallengeLeaderboard.is_correct.is_(True))
        .where(ChallengeLeaderboard.eligible.is_(True))
        .where(DailyChallenge.date >= start)
        .where(DailyChallenge.date < end)
        .group_by(ChallengeLeaderboard.user_id)
    ).all()
    ranked = sorted(
        rows,
        key=lambda row: (-int(row.hits), float(row.avg_ms or 0)),
    )
    raw = []
    for row in ranked:
        stats = db.get(UserStats, row.user_id)
        name = stats.display_name if stats and stats.display_name else alias_for(row.user_id)
        raw.append(
            {
                "user_id": row.user_id,
                "display_name": name,
                "correct_count": int(row.hits),
                "avg_time_ms": int(round(float(row.avg_ms or 0))),
            }
        )
    unique = collapse_prize_candidates(db, raw, source_month)[:limit]
    total = count_active_users(db)
    out = []
    for index, item in enumerate(unique, start=1):
        prize = prize_for_rank(index, total)
        out.append({**item, "rank": index, **prize})
    return out


def collapse_prize_candidates(
    db: Session, rows: list[dict], source_month: str
) -> list[dict]:
    if not rows:
        return []
    user_ids = [item["user_id"] for item in rows]
    clusters = anti_cheat.cluster_users(db, user_ids, by_ip=True)
    seen_roots: set[str] = set()
    unique: list[dict] = []
    for item in rows:
        uid = item["user_id"]
        root = clusters.get(uid, uid)
        if root in seen_roots:
            continue
        keys = anti_cheat.cluster_keys(db, uid)
        blocked = anti_cheat.lifetime_keys(keys) + anti_cheat.monthly_ip_keys(
            keys, source_month
        )
        if anti_cheat.already_granted(db, blocked):
            continue
        seen_roots.add(root)
        unique.append(item)
    return unique


def rank_map(db: Session, source_month: str) -> dict[str, dict]:
    return {item["user_id"]: item for item in monthly_standings(db, source_month, limit=100)}


def settle_month(db: Session, source_month: str | None = None) -> dict:
    allowed = previous_month_key()
    key = (source_month or "").strip() or allowed
    if key != allowed:
        raise ValueError(
            f"Settle yalnızca önceki ay ({allowed}) için çalışır; {key} kabul edilmez."
        )
    existing = db.get(MonthlyPrizeRun, key)
    meta = prize_meta(db)
    if existing:
        return {
            "source_month": key,
            "already": True,
            "winner_count": existing.winner_count,
            **meta,
        }

    standings = monthly_standings(db, key, limit=100)
    users = list(db.scalars(select(User)).all())
    for user in users:
        user.discount_percentage = 0
        user.is_free_next_month = False
        user.prize_rank = 0
        user.prize_source_month = ""

    awarded = 0
    for item in standings:
        if not item.get("tier"):
            continue
        user = get_or_create_user(db, item["user_id"])
        user.is_free_next_month = bool(item["is_free_next_month"])
        user.discount_percentage = int(item["discount_percentage"])
        user.prize_rank = int(item["rank"])
        user.prize_source_month = key
        keys = anti_cheat.cluster_keys(db, item["user_id"])
        grant_keys = anti_cheat.lifetime_keys(keys) + anti_cheat.monthly_ip_keys(
            keys, key
        )
        anti_cheat.record_grants(db, item["user_id"], key, grant_keys)
        if user.is_free_next_month:
            from app.services.billing import grant_pro_subscription

            grant_pro_subscription(db, user)
        awarded += 1

    run = MonthlyPrizeRun(source_month=key, winner_count=awarded)
    db.add(run)
    db.commit()
    return {
        "source_month": key,
        "already": False,
        "winner_count": awarded,
        **meta,
    }


def maybe_settle(db: Session) -> None:
    key = previous_month_key()
    if db.get(MonthlyPrizeRun, key) is None:
        settle_month(db, key)


def live_prize(db: Session, user_id: str) -> dict:
    current = month_key(today_istanbul())
    total = count_active_users(db)
    item = rank_map(db, current).get(user_id)
    if not item:
        return {**prize_for_rank(None, total), **prize_meta(db)}
    return {
        "monthly_rank": item["rank"],
        "is_free_next_month": item["is_free_next_month"],
        "discount_percentage": item["discount_percentage"],
        "badge": item["badge"],
        "tier": item["tier"],
        "correct_count": item["correct_count"],
        "avg_time_ms": item["avg_time_ms"],
        "source_month": current,
        "projected": True,
        **prize_meta(db),
    }


def settled_prize(db: Session, user_id: str) -> dict:
    user = get_or_create_user(db, user_id)
    total = count_active_users(db)
    prize = prize_for_rank(user.prize_rank or None, total)
    prize["source_month"] = user.prize_source_month or None
    prize["projected"] = False
    prize["is_free_next_month"] = bool(user.is_free_next_month)
    prize["discount_percentage"] = int(user.discount_percentage or 0)
    if user.is_free_next_month:
        prize["badge"] = "Bedava Ay 🎟️"
        prize["tier"] = "free"
        prize["monthly_rank"] = user.prize_rank or prize["monthly_rank"]
    elif user.discount_percentage:
        prize["badge"] = f"%{user.discount_percentage} İndirim Sahibi 🎟️"
        prize["tier"] = str(user.discount_percentage)
        prize["monthly_rank"] = user.prize_rank or prize["monthly_rank"]
    else:
        prize["badge"] = None
        prize["tier"] = None
    prize.update(prize_meta(db))
    return prize


def profile_prize(db: Session, user_id: str) -> dict:
    maybe_settle(db)
    live = live_prize(db, user_id)
    locked = settled_prize(db, user_id)
    meta = prize_meta(db)
    return {
        "live": live,
        "settled": locked,
        "badge": locked.get("badge") or live.get("badge"),
        "discount_percentage": locked.get("discount_percentage") or live.get("discount_percentage") or 0,
        "is_free_next_month": bool(locked.get("is_free_next_month") or live.get("is_free_next_month")),
        "monthly_rank": live.get("monthly_rank") or locked.get("monthly_rank"),
        **meta,
    }


def attach_badges(db: Session, entries: list[dict]) -> list[dict]:
    maybe_settle(db)
    lookup = rank_map(db, month_key(today_istanbul()))
    out = []
    for item in entries:
        extra = lookup.get(item["user_id"])
        row = dict(item)
        row["prize_badge"] = extra["badge"] if extra else None
        row["monthly_rank"] = extra["rank"] if extra else None
        out.append(row)
    return out
