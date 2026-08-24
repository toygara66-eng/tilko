"""Deneme kotası ve reklam destekli ücretsiz katman."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.database.models import AiConversion, User
from app.services.penalty import get_or_create_user
from app.services.ranks import RANK_ACEMI, address_for

FREE_AI_CREDITS = 7
TRIAL_DAYS = 7
AD_DAILY_LIMIT = 1
FREE_MAX_SECONDS = 600
AD_UNLOCK_SECONDS = 20 * 60
ISTANBUL_OFFSET = timezone(timedelta(hours=3))

def quota_message(title: str) -> str:
    return (
        f"Hey {title}, 7 ücretsiz video dönüştürme hakkını bitirdin! "
        "Sınırsız analiz için Tilko Pro'ya geç."
    )


def duration_message(title: str) -> str:
    return (
        f"Hey {title}, ücretsiz modda sadece 10 dakikaya kadar olan videoları "
        "çevirebilirsin!"
    )


def ad_required_message(title: str) -> str:
    return f"Hey {title}, önce reklamı izle, sonra çevir."


def ad_exhausted_message(title: str) -> str:
    return (
        f"Hey {title}, günlük hakkın bitti! "
        "Yarın gece yarısı 1 hak yenilenir — ya da Tilko Pro'ya geç."
    )


QUOTA_MESSAGE = quota_message(RANK_ACEMI)
DURATION_MESSAGE = duration_message(RANK_ACEMI)
AD_REQUIRED_MESSAGE = ad_required_message(RANK_ACEMI)
AD_EXHAUSTED_MESSAGE = ad_exhausted_message(RANK_ACEMI)


class QuotaExceededError(PermissionError):
    def __init__(self, message: str | None = None, *, title: str | None = None) -> None:
        super().__init__(message or quota_message(title or RANK_ACEMI))


class AdRequiredError(PermissionError):
    def __init__(self, message: str | None = None, *, title: str | None = None) -> None:
        super().__init__(message or ad_required_message(title or RANK_ACEMI))


class AdQuotaExceededError(PermissionError):
    def __init__(self, message: str | None = None, *, title: str | None = None) -> None:
        super().__init__(message or ad_exhausted_message(title or RANK_ACEMI))


class VideoTooLongError(ValueError):
    def __init__(self, message: str | None = None, *, title: str | None = None) -> None:
        super().__init__(message or duration_message(title or RANK_ACEMI))


@dataclass
class CreditReservation:
    charged: bool
    replay: bool
    is_premium: bool
    credits_left: int
    credit_limit: int = FREE_AI_CREDITS
    charge_kind: str = "none"
    is_ad_tier: bool = False
    is_in_trial: bool = False
    daily_ad_credits: int = 0
    daily_ad_limit: int = AD_DAILY_LIMIT
    trial_days_left: int = 0


def today_istanbul() -> date:
    try:
        return datetime.now(ZoneInfo("Europe/Istanbul")).date()
    except ZoneInfoNotFoundError:
        return datetime.now(ISTANBUL_OFFSET).date()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def is_in_trial_period(user: User) -> bool:
    if user.is_premium:
        return False
    started = _aware(user.created_at) or utcnow()
    try:
        start_day = started.astimezone(ZoneInfo("Europe/Istanbul")).date()
    except ZoneInfoNotFoundError:
        start_day = (started + timedelta(hours=3)).date()
    elapsed = (today_istanbul() - start_day).days
    return elapsed < TRIAL_DAYS


def trial_days_left(user: User) -> int:
    if user.is_premium or not is_in_trial_period(user):
        return 0
    started = _aware(user.created_at) or utcnow()
    try:
        start_day = started.astimezone(ZoneInfo("Europe/Istanbul")).date()
    except ZoneInfoNotFoundError:
        start_day = (started + timedelta(hours=3)).date()
    left = TRIAL_DAYS - (today_istanbul() - start_day).days
    return max(0, left)


def is_ad_tier(user: User) -> bool:
    return (not user.is_premium) and (not is_in_trial_period(user))


def reset_daily_ads(db: Session, user: User) -> User:
    if user.created_at is None:
        user.created_at = utcnow()
        db.commit()
        db.refresh(user)
    today = today_istanbul()
    result = db.execute(
        update(User)
        .where(User.user_id == user.user_id)
        .where(
            (User.last_credit_reset_date.is_(None))
            | (User.last_credit_reset_date != today)
        )
        .values(
            daily_ad_rewarded_credits=AD_DAILY_LIMIT,
            last_credit_reset_date=today,
        )
    )
    if result.rowcount:
        db.commit()
    db.refresh(user)
    return user


def ad_unlocked(user: User) -> bool:
    stamp = _aware(user.last_ad_unlock_at)
    if stamp is None:
        return False
    return (utcnow() - stamp).total_seconds() <= AD_UNLOCK_SECONDS


def snapshot(db: Session, user_id: str) -> dict:
    user = reset_daily_ads(db, get_or_create_user(db, user_id))
    from app.services.billing import public_status, refresh_entitlement

    refresh_entitlement(db, user)
    db.commit()
    in_trial = is_in_trial_period(user)
    ad_mode = is_ad_tier(user)
    if user.is_premium:
        left = FREE_AI_CREDITS
    elif in_trial:
        left = max(0, int(user.ai_credits_left or 0))
    else:
        left = max(0, int(user.daily_ad_rewarded_credits or 0))
    billing = public_status(user)
    return {
        "ai_credits_left": left,
        "ai_credit_limit": AD_DAILY_LIMIT if ad_mode else FREE_AI_CREDITS,
        "is_premium": bool(user.is_premium),
        "is_in_trial_period": in_trial,
        "is_ad_tier": ad_mode,
        "daily_ad_credits": max(0, int(user.daily_ad_rewarded_credits or 0)),
        "daily_ad_limit": AD_DAILY_LIMIT,
        "trial_days_left": trial_days_left(user),
        "subscription_status": billing["subscription_status"],
        "subscription_product_id": billing["product_id"],
        "subscription_expires_at": billing["expires_at"],
    }


def already_converted(db: Session, user_id: str, video_id: str) -> bool:
    row = db.scalars(
        select(AiConversion)
        .where(AiConversion.user_id == user_id)
        .where(AiConversion.video_id == video_id)
    ).first()
    return row is not None


def mark_ad_watched(db: Session, user_id: str) -> dict:
    user = reset_daily_ads(db, get_or_create_user(db, user_id))
    user.last_ad_unlock_at = utcnow()
    db.commit()
    return snapshot(db, user_id)


def enforce_duration(
    user: User,
    duration_seconds: int,
    db: Session | None = None,
) -> None:
    if is_ad_tier(user) and duration_seconds > FREE_MAX_SECONDS:
        title = address_for(db, user.user_id) if db is not None else RANK_ACEMI
        raise VideoTooLongError(title=title)


def _view_reservation(db: Session, user_id: str, **overrides) -> CreditReservation:
    view = snapshot(db, user_id)
    return CreditReservation(
        charged=bool(overrides.get("charged", False)),
        replay=bool(overrides.get("replay", False)),
        is_premium=bool(view["is_premium"]),
        credits_left=int(view["ai_credits_left"]),
        credit_limit=int(view["ai_credit_limit"]),
        charge_kind=str(overrides.get("charge_kind", "none")),
        is_ad_tier=bool(view["is_ad_tier"]),
        is_in_trial=bool(view["is_in_trial_period"]),
        daily_ad_credits=int(view["daily_ad_credits"]),
        daily_ad_limit=int(view["daily_ad_limit"]),
        trial_days_left=int(view["trial_days_left"]),
    )


def admin_bypass(db: Session, user_id: str) -> CreditReservation:
    """Admin anahtarıyla analiz: kredi/reklam düşmez."""
    get_or_create_user(db, user_id)
    return _view_reservation(db, user_id, charged=False, charge_kind="none")


def grant_credits(
    db: Session,
    user_id: str,
    *,
    credits: int | None = None,
    premium: bool | None = None,
    days: int = 31,
) -> dict:
    """Admin: deneme kredisini doldur veya Pro (süre + log ile) aç/kapa."""
    from app.services import billing as billing_service

    user = reset_daily_ads(db, get_or_create_user(db, user_id))
    if credits is not None:
        user.ai_credits_left = max(0, min(int(credits), FREE_AI_CREDITS * 5))
        db.add(user)
    if premium is True:
        billing_service.grant_pro_subscription(
            db,
            user,
            days=max(1, int(days or 31)),
            status="admin",
            source="admin",
            actor="admin_credits",
            note="Admin panelinden Pro açıldı.",
            commit=False,
        )
    elif premium is False:
        billing_service.revoke_pro_subscription(
            db,
            user,
            status="admin_revoked",
            source="admin",
            actor="admin_credits",
            note="Admin panelinden Pro kapatıldı.",
            commit=False,
        )
    db.commit()
    return snapshot(db, user_id)


def reserve(
    db: Session,
    user_id: str,
    video_id: str,
    *,
    ad_watched: bool = False,
) -> CreditReservation:
    user = reset_daily_ads(db, get_or_create_user(db, user_id))
    if user.is_premium:
        return _view_reservation(db, user_id, charged=False, charge_kind="none")
    if already_converted(db, user_id, video_id):
        return _view_reservation(db, user_id, charged=False, replay=True)

    if is_in_trial_period(user):
        result = db.execute(
            update(User)
            .where(User.user_id == user_id)
            .where(User.is_premium.is_(False))
            .where(User.ai_credits_left > 0)
            .values(ai_credits_left=User.ai_credits_left - 1)
        )
        db.commit()
        if result.rowcount:
            return _view_reservation(db, user_id, charged=True, charge_kind="trial")
        raise QuotaExceededError(title=address_for(db, user_id))

    if not (ad_watched or ad_unlocked(user)):
        raise AdRequiredError(title=address_for(db, user_id))
    result = db.execute(
        update(User)
        .where(User.user_id == user_id)
        .where(User.is_premium.is_(False))
        .where(User.daily_ad_rewarded_credits > 0)
        .values(daily_ad_rewarded_credits=User.daily_ad_rewarded_credits - 1)
    )
    db.commit()
    if result.rowcount:
        return _view_reservation(db, user_id, charged=True, charge_kind="ad")
    raise AdQuotaExceededError(title=address_for(db, user_id))


def refund(db: Session, user_id: str, reservation: CreditReservation) -> CreditReservation:
    if not reservation.charged:
        return snapshot_reservation(db, user_id, reservation)
    if reservation.charge_kind == "ad":
        db.execute(
            update(User)
            .where(User.user_id == user_id)
            .values(daily_ad_rewarded_credits=User.daily_ad_rewarded_credits + 1)
        )
        db.commit()
        user = get_or_create_user(db, user_id)
        if (user.daily_ad_rewarded_credits or 0) > AD_DAILY_LIMIT:
            user.daily_ad_rewarded_credits = AD_DAILY_LIMIT
            db.commit()
    else:
        db.execute(
            update(User)
            .where(User.user_id == user_id)
            .where(User.is_premium.is_(False))
            .values(ai_credits_left=User.ai_credits_left + 1)
        )
        db.commit()
        user = get_or_create_user(db, user_id)
        if user.ai_credits_left > FREE_AI_CREDITS:
            user.ai_credits_left = FREE_AI_CREDITS
            db.commit()
    return snapshot_reservation(db, user_id, reservation, charged=False)


def confirm(db: Session, user_id: str, video_id: str, reservation: CreditReservation) -> CreditReservation:
    if reservation.replay or reservation.is_premium:
        return snapshot_reservation(db, user_id, reservation)
    if not reservation.charged:
        return snapshot_reservation(db, user_id, reservation)
    db.add(AiConversion(user_id=user_id, video_id=video_id))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return refund(db, user_id, reservation)
    return snapshot_reservation(db, user_id, reservation)


def refund_charged(
    db: Session,
    user_id: str,
    charge_kind: str,
) -> None:
    """Paylaşılan iş başarısız olunca takipçi iadesi (reservation objesi yok)."""
    kind = (charge_kind or "trial").strip()
    if kind == "ad":
        db.execute(
            update(User)
            .where(User.user_id == user_id)
            .values(daily_ad_rewarded_credits=User.daily_ad_rewarded_credits + 1)
        )
        db.commit()
        user = get_or_create_user(db, user_id)
        if (user.daily_ad_rewarded_credits or 0) > AD_DAILY_LIMIT:
            user.daily_ad_rewarded_credits = AD_DAILY_LIMIT
            db.commit()
        return
    if kind == "none":
        return
    db.execute(
        update(User)
        .where(User.user_id == user_id)
        .where(User.is_premium.is_(False))
        .values(ai_credits_left=User.ai_credits_left + 1)
    )
    db.commit()
    user = get_or_create_user(db, user_id)
    if user.ai_credits_left > FREE_AI_CREDITS:
        user.ai_credits_left = FREE_AI_CREDITS
        db.commit()


def confirm_charged(
    db: Session,
    user_id: str,
    video_id: str,
    charge_kind: str,
) -> None:
    if not charge_kind or charge_kind == "none":
        return
    if already_converted(db, user_id, video_id):
        # Çift rezervasyon yarışı: conversion var, kredi iade et.
        refund_charged(db, user_id, charge_kind)
        return
    db.add(AiConversion(user_id=user_id, video_id=video_id))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        refund_charged(db, user_id, charge_kind)


def snapshot_reservation(
    db: Session,
    user_id: str,
    reservation: CreditReservation,
    *,
    charged: bool | None = None,
) -> CreditReservation:
    view = snapshot(db, user_id)
    return CreditReservation(
        charged=reservation.charged if charged is None else charged,
        replay=reservation.replay,
        is_premium=bool(view["is_premium"]),
        credits_left=int(view["ai_credits_left"]),
        credit_limit=int(view["ai_credit_limit"]),
        charge_kind=reservation.charge_kind if charged is None else "none",
        is_ad_tier=bool(view["is_ad_tier"]),
        is_in_trial=bool(view["is_in_trial_period"]),
        daily_ad_credits=int(view["daily_ad_credits"]),
        daily_ad_limit=int(view["daily_ad_limit"]),
        trial_days_left=int(view["trial_days_left"]),
    )


def overlay_view(view: dict) -> dict:
    return {
        "ai_credits_left": int(view.get("ai_credits_left") or 0),
        "ai_credit_limit": int(view.get("ai_credit_limit") or 7),
        "is_premium": bool(view.get("is_premium")),
        "is_in_trial_period": bool(view.get("is_in_trial_period")),
        "is_ad_tier": bool(view.get("is_ad_tier")),
        "daily_ad_credits": int(view.get("daily_ad_credits") or 0),
        "daily_ad_limit": int(view.get("daily_ad_limit") or 1),
        "trial_days_left": int(view.get("trial_days_left") or 0),
    }


def overlay(reservation: CreditReservation) -> dict:
    return {
        "ai_credits_left": reservation.credits_left,
        "ai_credit_limit": reservation.credit_limit,
        "is_premium": reservation.is_premium,
        "is_in_trial_period": reservation.is_in_trial,
        "is_ad_tier": reservation.is_ad_tier,
        "daily_ad_credits": reservation.daily_ad_credits,
        "daily_ad_limit": reservation.daily_ad_limit,
        "trial_days_left": reservation.trial_days_left,
    }
