"""Sazan Avı anti-cheat: sunucu süresi, hız tabanı, cihaz/IP kümeleme."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import (
    ChallengeLeaderboard,
    ChallengeSession,
    DeviceSighting,
    PrizeGrant,
    User,
)

MIN_READING_MS = 3000
HARD_MIN_MS = 2000
CHARS_PER_SEC = 40
MAX_READING_MS = 5000
DEVICE_RE = re.compile(r"^[A-Za-z0-9_\-:]{8,64}$")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def hash_ip(ip: str) -> str:
    value = (ip or "").strip()
    if not value:
        return ""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]


def client_ip(request) -> str:
    if request is None:
        return ""
    forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    if forwarded:
        return forwarded
    if request.client and request.client.host:
        return request.client.host
    return ""


def normalize_device_id(raw: str | None) -> str:
    value = (raw or "").strip()
    if not DEVICE_RE.match(value):
        return ""
    return value[:64]


def normalize_identity(raw: str | None) -> str:
    value = (raw or "").strip()
    if len(value) < 16 or len(value) > 128:
        return ""
    return value[:128]


def min_reading_ms(question_text: str, options: dict[str, str] | None = None) -> int:
    parts = [question_text or ""]
    for text in (options or {}).values():
        parts.append(str(text))
    chars = len(" ".join(parts).strip())
    estimated = int(chars / CHARS_PER_SEC * 1000)
    return max(MIN_READING_MS, min(estimated, MAX_READING_MS))


def elapsed_ms(started_at: datetime, finished_at: datetime) -> int:
    start = started_at
    end = finished_at
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    delta = (end - start).total_seconds() * 1000
    return max(0, int(round(delta)))


def is_too_fast(elapsed: int, question_text: str, options: dict[str, str] | None = None) -> bool:
    return elapsed < min_reading_ms(question_text, options)


def is_cheated(elapsed: int, question_text: str, options: dict[str, str] | None = None) -> bool:
    """2 sn altı veya okuma hızına aykırı cevap — diskalifiye."""
    if elapsed < HARD_MIN_MS:
        return True
    return is_too_fast(elapsed, question_text, options)


def remember_sighting(
    db: Session,
    *,
    user_id: str,
    device_id: str,
    ip_hash: str,
) -> None:
    if not user_id:
        return
    existing = db.scalars(
        select(DeviceSighting)
        .where(DeviceSighting.user_id == user_id)
        .where(DeviceSighting.device_id == (device_id or ""))
        .where(DeviceSighting.ip_hash == (ip_hash or ""))
    ).first()
    if existing:
        existing.last_seen_at = utcnow()
        return
    db.add(
        DeviceSighting(
            user_id=user_id,
            device_id=device_id or "",
            ip_hash=ip_hash or "",
        )
    )


def start_session(
    db: Session,
    *,
    user_id: str,
    challenge_id: int,
    device_id: str,
    ip_hash: str,
) -> ChallengeSession:
    row = db.scalars(
        select(ChallengeSession)
        .where(ChallengeSession.user_id == user_id)
        .where(ChallengeSession.challenge_id == challenge_id)
    ).first()
    remember_sighting(db, user_id=user_id, device_id=device_id, ip_hash=ip_hash)
    if row:
        if device_id and not row.device_id:
            row.device_id = device_id
        if ip_hash and not row.ip_hash:
            row.ip_hash = ip_hash
        db.commit()
        db.refresh(row)
        return row
    row = ChallengeSession(
        user_id=user_id,
        challenge_id=challenge_id,
        started_at=utcnow(),
        device_id=device_id,
        ip_hash=ip_hash,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_session(db: Session, user_id: str, challenge_id: int) -> ChallengeSession | None:
    return db.scalars(
        select(ChallengeSession)
        .where(ChallengeSession.user_id == user_id)
        .where(ChallengeSession.challenge_id == challenge_id)
    ).first()


def user_links(db: Session, user_ids: list[str] | None = None) -> list[DeviceSighting]:
    query = select(DeviceSighting)
    if user_ids:
        query = query.where(DeviceSighting.user_id.in_(user_ids))
    return list(db.scalars(query).all())


def cluster_users(db: Session, user_ids: list[str], *, by_ip: bool = True) -> dict[str, str]:
    """Aynı cihaz / kimlik / (isteğe bağlı) IP paylaşan hesapları tek kümeye bağlar."""
    parent = {uid: uid for uid in user_ids}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        pa, pb = find(a), find(b)
        if pa != pb:
            parent[pb] = pa

    users = list(db.scalars(select(User).where(User.user_id.in_(user_ids))).all())
    identity_map: dict[str, str] = {}
    for user in users:
        ident = (user.identity_hash or "").strip()
        if ident:
            if ident in identity_map:
                union(user.user_id, identity_map[ident])
            else:
                identity_map[ident] = user.user_id

    sightings = user_links(db, user_ids)
    device_map: dict[str, str] = {}
    ip_map: dict[str, str] = {}
    for row in sightings:
        if row.user_id not in parent:
            parent[row.user_id] = row.user_id
        if row.device_id:
            if row.device_id in device_map:
                union(row.user_id, device_map[row.device_id])
            else:
                device_map[row.device_id] = row.user_id
        if by_ip and row.ip_hash:
            if row.ip_hash in ip_map:
                union(row.user_id, ip_map[row.ip_hash])
            else:
                ip_map[row.ip_hash] = row.user_id

    return {uid: find(uid) for uid in parent}


def cluster_keys(db: Session, user_id: str) -> list[str]:
    keys = [f"user:{user_id}"]
    user = db.get(User, user_id)
    if user and user.identity_hash:
        keys.append(f"id:{user.identity_hash}")
    for row in user_links(db, [user_id]):
        if row.device_id:
            keys.append(f"device:{row.device_id}")
        if row.ip_hash:
            keys.append(f"ip:{row.ip_hash}")
    return sorted(set(keys))


def lifetime_keys(keys: list[str]) -> list[str]:
    return [key for key in keys if key.startswith("device:") or key.startswith("id:")]


def monthly_ip_keys(keys: list[str], source_month: str) -> list[str]:
    return [f"{key}:{source_month}" for key in keys if key.startswith("ip:")]


def already_granted(db: Session, keys: list[str]) -> bool:
    if not keys:
        return False
    row = db.scalars(select(PrizeGrant).where(PrizeGrant.identity_key.in_(keys))).first()
    return row is not None


def record_grants(db: Session, user_id: str, source_month: str, keys: list[str]) -> None:
    for key in keys:
        exists = db.scalars(select(PrizeGrant).where(PrizeGrant.identity_key == key)).first()
        if exists:
            continue
        db.add(
            PrizeGrant(
                identity_key=key,
                user_id=user_id,
                source_month=source_month,
            )
        )


def collapse_eligible(
    rows: list[ChallengeLeaderboard],
) -> list[ChallengeLeaderboard]:
    """Aynı cihazdan birden fazla hesabı günlük listeden düşürür."""
    seen_device: set[str] = set()
    kept: list[ChallengeLeaderboard] = []
    for row in rows:
        device = (row.device_id or "").strip()
        if device:
            if device in seen_device:
                continue
            seen_device.add(device)
        kept.append(row)
    return kept
