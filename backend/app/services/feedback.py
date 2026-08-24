"""Kullanıcı öneri ve geri bildirimi."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import User, UserFeedback
from app.services.ranks import address_for

STATUS_PENDING = "pending"
STATUS_DONE = "done"
STATUS_ARCHIVED = "archived"
CATEGORIES = ("feature", "ui_ux", "general")
MESSAGE_MIN = 8
MESSAGE_MAX = 2000
CATEGORY_LABELS = {
    "feature": "Özellik önerisi",
    "ui_ux": "Tasarım / kullanım",
    "general": "Genel",
}


def submit_feedback(
    db: Session,
    *,
    user_id: str,
    category: str,
    message: str,
) -> dict:
    uid = (user_id or "").strip()
    kind = (category or "").strip().lower().replace("-", "_")
    if kind == "uiux":
        kind = "ui_ux"
    text = " ".join((message or "").split())
    if not uid:
        raise ValueError("Kullanıcı kimliği gerekli.")
    if kind not in CATEGORIES:
        raise ValueError("Kategori geçersiz. Özellik, tasarım veya diğer seç.")
    if len(text) < MESSAGE_MIN:
        raise ValueError("Fikrini biraz daha açık yazar mısın? En az birkaç kelime.")
    if len(text) > MESSAGE_MAX:
        raise ValueError("Mesaj çok uzun. 2000 karakteri geçme.")

    row = UserFeedback(
        user_id=uid[:128],
        category=kind,
        message=text,
        status=STATUS_PENDING,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    title = address_for(db, uid)
    return {
        "id": row.id,
        "category": row.category,
        "status": row.status,
        "message": f"Teşekkürler {title}, fikrin inceleme kuyruğuna eklendi!",
    }


def _iso(value) -> str | None:
    if value is None:
        return None
    try:
        return value.isoformat()
    except Exception:  # noqa: BLE001
        return str(value)


def list_feedback(db: Session, *, limit: int = 100, status: str = "") -> dict:
    cap = max(1, min(int(limit or 100), 300))
    stmt = select(UserFeedback).order_by(UserFeedback.created_at.desc()).limit(cap)
    want = (status or "").strip().lower()
    if want in {STATUS_PENDING, STATUS_DONE, STATUS_ARCHIVED}:
        stmt = (
            select(UserFeedback)
            .where(UserFeedback.status == want)
            .order_by(UserFeedback.created_at.desc())
            .limit(cap)
        )
    rows = list(db.scalars(stmt).all())
    items: list[dict] = []
    for row in rows:
        user = db.get(User, row.user_id)
        items.append(
            {
                "id": int(row.id),
                "user_id": row.user_id,
                "display_name": (getattr(user, "display_name", None) or "").strip()
                if user
                else "",
                "email": (getattr(user, "email", None) or "").strip() if user else "",
                "phone": (getattr(user, "phone", None) or "").strip() if user else "",
                "category": row.category,
                "category_label": CATEGORY_LABELS.get(row.category, row.category),
                "message": row.message or "",
                "status": row.status or STATUS_PENDING,
                "created_at": _iso(row.created_at),
            }
        )
    return {"items": items, "count": len(items)}


def set_feedback_status(db: Session, feedback_id: int, status: str) -> dict:
    want = (status or "").strip().lower()
    if want not in {STATUS_PENDING, STATUS_DONE, STATUS_ARCHIVED}:
        raise ValueError("Durum: pending, done veya archived olmalı.")
    row = db.get(UserFeedback, int(feedback_id))
    if row is None:
        raise ValueError("Geri bildirim bulunamadı.")
    row.status = want
    db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "id": int(row.id),
        "status": row.status,
        "message": f"Durum güncellendi: {want}",
    }
