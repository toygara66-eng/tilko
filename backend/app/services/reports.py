"""Hatalı soru bildirimi."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.database.models import ReportedQuestion
from app.services.ranks import address_for

STATUS_PENDING = "pending"
REASON_MIN = 8
REASON_MAX = 2000


def report_question(db: Session, *, user_id: str, question_id: str, reason_text: str) -> dict:
    uid = (user_id or "").strip()
    qid = (question_id or "").strip()
    reason = " ".join((reason_text or "").split())
    if not uid:
        raise ValueError("Kullanıcı kimliği gerekli.")
    if not qid:
        raise ValueError("Soru kimliği gerekli.")
    if len(reason) < REASON_MIN:
        raise ValueError("Hatayı biraz daha açık yazar mısın? En az birkaç kelime.")
    if len(reason) > REASON_MAX:
        raise ValueError("Açıklama çok uzun. 2000 karakteri geçme.")

    row = ReportedQuestion(
        question_id=qid[:128],
        user_id=uid[:128],
        reason_text=reason,
        status=STATUS_PENDING,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    title = address_for(db, uid)
    return {
        "id": row.id,
        "question_id": row.question_id,
        "status": row.status,
        "message": f"Geri bildirimin alındı {title}, inceleniyor!",
    }
