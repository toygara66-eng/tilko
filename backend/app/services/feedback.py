"""Kullanıcı öneri ve geri bildirimi."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.database.models import UserFeedback
from app.services.ranks import address_for

STATUS_PENDING = "pending"
CATEGORIES = ("feature", "ui_ux", "general")
MESSAGE_MIN = 8
MESSAGE_MAX = 2000


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
