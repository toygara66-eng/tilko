"""Analiz notları ve soruları ders ders birikir; kaybolmaz."""

from __future__ import annotations

import hashlib
import json
import logging

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.models import SavedNotebookItem
from app.services.exams import SUBJECTS_BY_FAMILY, subjects_for

logger = logging.getLogger(__name__)


def canonical_subject(raw: str | None, exam_target: str | None = None) -> str:
    text = (raw or "").strip()
    if not text:
        return "Genel"
    needle = text.casefold()
    ordered: list[str] = []
    seen: set[str] = set()
    for name in subjects_for(exam_target) + [
        item for names in SUBJECTS_BY_FAMILY.values() for item in names
    ]:
        if name not in seen:
            seen.add(name)
            ordered.append(name)
    for name in ordered:
        if name.casefold() == needle:
            return name
    return text[:64]


def _dump(item) -> dict:
    if item is None:
        return {}
    if hasattr(item, "model_dump"):
        return item.model_dump()
    if isinstance(item, dict):
        return dict(item)
    return {}


def _fingerprint(kind: str, video_id: str, payload: dict) -> str:
    title = str(payload.get("title") or payload.get("text") or "")[:120]
    stamp = str(payload.get("timestamp") or payload.get("timestamp_label") or "")
    raw = f"{kind}|{video_id}|{stamp}|{title}".encode("utf-8", errors="ignore")
    return hashlib.sha1(raw).hexdigest()


def ingest(
    db: Session,
    *,
    user_id: str,
    subject: str | None,
    video_id: str,
    video_url: str,
    notes: list | None,
    questions: list | None,
    persona: dict | None = None,
    exam_target: str | None = None,
) -> int:
    uid = (user_id or "").strip()
    vid = (video_id or "").strip()
    if not uid or not vid:
        return 0
    label = canonical_subject(subject, exam_target)
    watch = (video_url or "").strip()
    added = 0
    added += _upsert_many(
        db,
        user_id=uid,
        kind="note",
        subject=label,
        video_id=vid,
        video_url=watch,
        items=notes or [],
        extra={},
    )
    added += _upsert_many(
        db,
        user_id=uid,
        kind="question",
        subject=label,
        video_id=vid,
        video_url=watch,
        items=questions or [],
        extra={"teacher_persona": persona or {}},
    )
    if added:
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            # Yarış: aynı not iki kez yazıldıysa satır satır dene, hepsini kaybetme.
            return _upsert_many_safe(
                db,
                user_id=uid,
                kind="note",
                subject=label,
                video_id=vid,
                video_url=watch,
                items=notes or [],
                extra={},
            ) + _upsert_many_safe(
                db,
                user_id=uid,
                kind="question",
                subject=label,
                video_id=vid,
                video_url=watch,
                items=questions or [],
                extra={"teacher_persona": persona or {}},
            )
    return added


def _upsert_many_safe(
    db: Session,
    *,
    user_id: str,
    kind: str,
    subject: str,
    video_id: str,
    video_url: str,
    items: list,
    extra: dict,
) -> int:
    added = 0
    for item in items:
        payload = _dump(item)
        if not payload:
            continue
        payload.update(extra)
        fp = _fingerprint(kind, video_id, payload)
        exists = db.scalar(
            select(SavedNotebookItem.id).where(
                SavedNotebookItem.user_id == user_id,
                SavedNotebookItem.fingerprint == fp,
            )
        )
        if exists:
            continue
        title = str(payload.get("title") or payload.get("text") or "")[:256]
        try:
            stamp = int(float(payload.get("timestamp") or 0))
        except (TypeError, ValueError):
            stamp = 0
        try:
            db.add(
                SavedNotebookItem(
                    user_id=user_id,
                    kind=kind,
                    subject=subject,
                    video_id=video_id,
                    video_url=video_url,
                    fingerprint=fp,
                    title=title,
                    timestamp=stamp,
                    payload_json=json.dumps(payload, ensure_ascii=False),
                )
            )
            db.commit()
            added += 1
        except IntegrityError:
            db.rollback()
    return added


def _upsert_many(
    db: Session,
    *,
    user_id: str,
    kind: str,
    subject: str,
    video_id: str,
    video_url: str,
    items: list,
    extra: dict,
) -> int:
    added = 0
    for item in items:
        payload = _dump(item)
        if not payload:
            continue
        payload.update(extra)
        fp = _fingerprint(kind, video_id, payload)
        exists = db.scalar(
            select(SavedNotebookItem.id).where(
                SavedNotebookItem.user_id == user_id,
                SavedNotebookItem.fingerprint == fp,
            )
        )
        if exists:
            continue
        title = str(payload.get("title") or payload.get("text") or "")[:256]
        try:
            stamp = int(float(payload.get("timestamp") or 0))
        except (TypeError, ValueError):
            stamp = 0
        db.add(
            SavedNotebookItem(
                user_id=user_id,
                kind=kind,
                subject=subject,
                video_id=video_id,
                video_url=video_url,
                fingerprint=fp,
                title=title,
                timestamp=stamp,
                payload_json=json.dumps(payload, ensure_ascii=False),
            )
        )
        added += 1
    return added


def subject_counts(db: Session, user_id: str) -> list[dict]:
    rows = db.execute(
        select(
            SavedNotebookItem.subject,
            SavedNotebookItem.kind,
            func.count(SavedNotebookItem.id),
        )
        .where(SavedNotebookItem.user_id == user_id)
        .group_by(SavedNotebookItem.subject, SavedNotebookItem.kind)
    ).all()
    bag: dict[str, dict] = {}
    for subject, kind, count in rows:
        name = subject or "Genel"
        slot = bag.setdefault(name, {"name": name, "note_count": 0, "question_count": 0})
        if kind == "question":
            slot["question_count"] = int(count)
        else:
            slot["note_count"] = int(count)
    return sorted(bag.values(), key=lambda item: item["name"].casefold())


def list_items(
    db: Session,
    user_id: str,
    *,
    subject: str | None = None,
    exam_target: str | None = None,
) -> dict:
    uid = (user_id or "").strip()
    counts = subject_counts(db, uid)
    query = select(SavedNotebookItem).where(SavedNotebookItem.user_id == uid)
    if (subject or "").strip() and (subject or "").strip().casefold() not in {
        "tümü",
        "tumu",
        "all",
    }:
        query = query.where(
            SavedNotebookItem.subject == canonical_subject(subject, exam_target)
        )
    query = query.order_by(
        SavedNotebookItem.created_at.desc(),
        SavedNotebookItem.timestamp.asc(),
        SavedNotebookItem.id.asc(),
    )
    notes: list[dict] = []
    questions: list[dict] = []
    for row in db.scalars(query).all():
        public = _to_public(row)
        if not public:
            continue
        if row.kind == "question":
            questions.append(public)
        else:
            notes.append(public)
    return {
        "user_id": uid,
        "subject": (subject or "").strip() or None,
        "subjects": counts,
        "notes": notes,
        "questions": questions,
    }


def _to_public(row: SavedNotebookItem) -> dict | None:
    from app.services.youtube import build_watch_url, format_timestamp_label

    try:
        payload = json.loads(row.payload_json or "{}")
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        return None
    options = payload.get("options") or {}
    if isinstance(options, list):
        letters = ("A", "B", "C", "D", "E")
        options = {
            letters[i]: str(val)
            for i, val in enumerate(options)
            if i < len(letters)
        }
    if not isinstance(options, dict):
        options = {}
    points = payload.get("key_points") or []
    if not isinstance(points, list):
        points = [points] if points else []
    persona = payload.get("teacher_persona") or {}
    if not isinstance(persona, dict):
        persona = {"catchphrases": [], "tone": "öğretici, net"}
    stamp = int(row.timestamp or 0)
    watch = row.video_url or str(payload.get("video_url") or "")
    timed = str(payload.get("video_url_with_t") or "") or (
        build_watch_url(row.video_id, stamp) if row.video_id else watch
    )
    text = str(payload.get("text") or payload.get("detail") or row.title or "").strip()
    return {
        **payload,
        "saved_id": row.id,
        "subject": row.subject,
        "video_url": watch,
        "id": str(payload.get("id") or f"{row.kind}_{row.id}"),
        "title": str(payload.get("title") or row.title or "") or "Not",
        "text": text or str(payload.get("title") or row.title or "Not"),
        "key_points": [str(p).strip() for p in points if str(p).strip()],
        "mnemonic": str(payload.get("mnemonic") or ""),
        "exam_tip": str(payload.get("exam_tip") or ""),
        "timestamp": stamp,
        "timestamp_label": str(payload.get("timestamp_label") or format_timestamp_label(stamp)),
        "video_url_with_t": timed or watch or "",
        "options": {str(k): str(v) for k, v in options.items()},
        "correct": str(payload.get("correct") or ""),
        "explanation": str(payload.get("explanation") or ""),
        "trap_explanation": str(payload.get("trap_explanation") or ""),
        "topic": str(payload.get("topic") or ""),
        "difficulty": str(payload.get("difficulty") or ""),
        "teacher_persona": {
            "catchphrases": list(persona.get("catchphrases") or []),
            "tone": str(persona.get("tone") or "öğretici, net"),
        },
    }
