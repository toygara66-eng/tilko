"""Analiz notları ve soruları ders ders birikir; kaybolmaz."""

from __future__ import annotations

import hashlib
import json
import logging

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.models import NotebookSession, SavedNotebookItem
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


def ensure_session(
    db: Session,
    *,
    user_id: str,
    subject: str,
    video_id: str,
    video_url: str = "",
    label: str | None = None,
) -> NotebookSession | None:
    uid = (user_id or "").strip()
    vid = (video_id or "").strip()
    subj = (subject or "").strip() or "Genel"
    if not uid or not vid:
        return None
    row = db.scalar(
        select(NotebookSession).where(
            NotebookSession.user_id == uid,
            NotebookSession.subject == subj,
            NotebookSession.video_id == vid,
        )
    )
    if row:
        if video_url and not row.video_url:
            row.video_url = video_url[:256]
        if label is not None:
            cleaned = (label or "").strip()[:160]
            if cleaned:
                row.label = cleaned
        db.add(row)
        return row
    from datetime import datetime

    stamp = datetime.now().strftime("%d.%m.%Y")
    default = (label or "").strip()[:160] or f"{subj} notları · {stamp}"
    row = NotebookSession(
        user_id=uid,
        subject=subj,
        video_id=vid,
        video_url=(video_url or "")[:256],
        label=default[:160],
    )
    db.add(row)
    return row


def rename_session(
    db: Session,
    *,
    user_id: str,
    subject: str,
    video_id: str,
    label: str,
    exam_target: str | None = None,
    video_url: str = "",
) -> dict:
    uid = (user_id or "").strip()
    vid = (video_id or "").strip()
    name = (label or "").strip()[:160]
    if not uid or not vid:
        raise ValueError("user_id ve video_id gerekli.")
    if len(name) < 2:
        raise ValueError("İsim en az 2 karakter olmalı.")
    subj = canonical_subject(subject, exam_target)
    row = ensure_session(
        db,
        user_id=uid,
        subject=subj,
        video_id=vid,
        video_url=video_url,
        label=name,
    )
    if row is None:
        raise ValueError("Oturum oluşturulamadı.")
    db.commit()
    db.refresh(row)
    return _session_public(row)


def list_sessions(
    db: Session,
    user_id: str,
    *,
    subject: str | None = None,
    exam_target: str | None = None,
) -> list[dict]:
    uid = (user_id or "").strip()
    query = select(NotebookSession).where(NotebookSession.user_id == uid)
    if (subject or "").strip():
        query = query.where(
            NotebookSession.subject == canonical_subject(subject, exam_target)
        )
    query = query.order_by(NotebookSession.updated_at.desc(), NotebookSession.id.desc())
    rows = list(db.scalars(query).all())

    # Eski kayıtlar için session yoksa video_id'lerden üret
    items_q = select(SavedNotebookItem).where(SavedNotebookItem.user_id == uid)
    if (subject or "").strip():
        items_q = items_q.where(
            SavedNotebookItem.subject == canonical_subject(subject, exam_target)
        )
    existing = {(r.subject, r.video_id) for r in rows}
    for item in db.scalars(items_q).all():
        key = (item.subject or "Genel", item.video_id or "")
        if not key[1] or key in existing:
            continue
        created = ensure_session(
            db,
            user_id=uid,
            subject=key[0],
            video_id=key[1],
            video_url=item.video_url or "",
        )
        if created:
            existing.add(key)
            rows.append(created)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()

    # Sayım
    count_rows = db.execute(
        select(
            SavedNotebookItem.subject,
            SavedNotebookItem.video_id,
            SavedNotebookItem.kind,
            func.count(SavedNotebookItem.id),
        )
        .where(SavedNotebookItem.user_id == uid)
        .group_by(
            SavedNotebookItem.subject,
            SavedNotebookItem.video_id,
            SavedNotebookItem.kind,
        )
    ).all()
    tallies: dict[tuple[str, str], dict[str, int]] = {}
    for subj, vid, kind, count in count_rows:
        slot = tallies.setdefault(
            (subj or "Genel", vid or ""),
            {"note_count": 0, "question_count": 0},
        )
        if kind == "question":
            slot["question_count"] = int(count)
        else:
            slot["note_count"] = int(count)

    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for row in sorted(
        rows,
        key=lambda r: (r.updated_at or r.created_at or _epoch(), r.id),
        reverse=True,
    ):
        key = (row.subject or "Genel", row.video_id or "")
        if key in seen or not key[1]:
            continue
        seen.add(key)
        pub = _session_public(row)
        counts = tallies.get(key) or {"note_count": 0, "question_count": 0}
        pub.update(counts)
        if pub["note_count"] or pub["question_count"]:
            out.append(pub)
    return out


def _epoch():
    from datetime import datetime, timezone

    return datetime(1970, 1, 1, tzinfo=timezone.utc)


def _session_public(row: NotebookSession) -> dict:
    return {
        "id": row.id,
        "subject": row.subject or "Genel",
        "video_id": row.video_id or "",
        "video_url": row.video_url or "",
        "label": (row.label or "").strip() or "İsimsiz not seti",
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "note_count": 0,
        "question_count": 0,
    }


def session_notes(
    db: Session,
    user_id: str,
    *,
    subject: str,
    video_id: str,
    exam_target: str | None = None,
) -> dict:
    """Bir isimli setin not/soruları."""
    uid = (user_id or "").strip()
    vid = (video_id or "").strip()
    subj = canonical_subject(subject, exam_target)
    query = (
        select(SavedNotebookItem)
        .where(
            SavedNotebookItem.user_id == uid,
            SavedNotebookItem.subject == subj,
            SavedNotebookItem.video_id == vid,
        )
        .order_by(
            SavedNotebookItem.timestamp.asc(),
            SavedNotebookItem.id.asc(),
        )
    )
    notes: list[dict] = []
    questions: list[dict] = []
    label_map = _label_map(db, uid)
    for row in db.scalars(query).all():
        public = _to_public(row, label_map)
        if not public:
            continue
        if row.kind == "question":
            questions.append(public)
        else:
            notes.append(public)
    session = db.scalar(
        select(NotebookSession).where(
            NotebookSession.user_id == uid,
            NotebookSession.subject == subj,
            NotebookSession.video_id == vid,
        )
    )
    return {
        "user_id": uid,
        "subject": subj,
        "video_id": vid,
        "label": (session.label if session else "") or f"{subj} notları",
        "video_url": (session.video_url if session else "")
        or (notes[0].get("video_url") if notes else "")
        or (questions[0].get("video_url") if questions else ""),
        "notes": notes,
        "questions": questions,
    }


def _pdf_font_paths() -> tuple[str, str]:
    """Türkçe destekli TTF: proje asset → sistem fontları."""
    from pathlib import Path

    here = Path(__file__).resolve().parents[1] / "assets" / "fonts"
    candidates_regular = [
        here / "DejaVuSans.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/segoeui.ttf"),
    ]
    candidates_bold = [
        here / "DejaVuSans-Bold.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf"),
        Path("C:/Windows/Fonts/segoeuib.ttf"),
    ]
    regular = next((str(p) for p in candidates_regular if p.exists()), "")
    bold = next((str(p) for p in candidates_bold if p.exists()), regular)
    if not regular:
        raise RuntimeError("PDF için Unicode font bulunamadı.")
    return regular, bold or regular


def build_notes_pdf_bytes(
    *,
    label: str,
    subject: str,
    notes: list[dict],
    questions: list[dict] | None = None,
) -> bytes:
    """Türkçe destekli basit PDF (fpdf2)."""
    from fpdf import FPDF

    regular, bold = _pdf_font_paths()
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.set_margins(14, 14, 14)
    pdf.add_page()
    pdf.add_font("TilkoSans", "", regular)
    pdf.add_font("TilkoSans", "B", bold)
    usable = pdf.w - pdf.l_margin - pdf.r_margin

    def write(text: str, *, weight: str = "", size: int = 11) -> None:
        pdf.set_font("TilkoSans", weight, size)
        pdf.multi_cell(usable, 6, text or " ")

    write("TİLKO — Ders Notları", weight="B", size=16)
    pdf.ln(2)
    write(f"{subject} · {label}", weight="B", size=13)
    pdf.ln(4)

    if not notes:
        write("Bu sette henüz not yok.")
    for index, note in enumerate(notes, start=1):
        title = str(note.get("title") or f"Not {index}")
        write(f"{index}. {title}", weight="B", size=12)
        detail = str(note.get("text") or note.get("detail") or "").strip()
        if detail:
            write(detail, size=10)
        for point in note.get("key_points") or []:
            line = str(point).strip()
            if line:
                write(f"• {line}", size=10)
        tip = str(note.get("exam_tip") or "").strip()
        if tip:
            write(f"Tuzak: {tip}", size=10)
        mnemonic = str(note.get("mnemonic") or "").strip()
        if mnemonic:
            write(f"Hafıza: {mnemonic}", size=10)
        pdf.ln(3)

    extra_q = questions or []
    if extra_q:
        pdf.add_page()
        write("Soru bankası", weight="B", size=14)
        pdf.ln(2)
        for index, item in enumerate(extra_q, start=1):
            write(f"S{index}. {item.get('text') or ''}", weight="B", size=11)
            options = item.get("options") or {}
            if isinstance(options, dict):
                for letter, text in options.items():
                    mark = " ✓" if str(letter) == str(item.get("correct") or "") else ""
                    write(f"  {letter}) {text}{mark}", size=10)
            expl = str(item.get("explanation") or "").strip()
            if expl:
                write(f"Açıklama: {expl}", size=9)
            pdf.ln(2)

    out = pdf.output()
    if isinstance(out, (bytes, bytearray)):
        return bytes(out)
    return str(out).encode("latin-1", errors="ignore")


def _label_map(db: Session, user_id: str) -> dict[tuple[str, str], str]:
    rows = db.scalars(
        select(NotebookSession).where(NotebookSession.user_id == user_id)
    ).all()
    return {
        (r.subject or "Genel", r.video_id or ""): (r.label or "").strip()
        for r in rows
        if r.video_id
    }


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
    session_label: str | None = None,
) -> int:
    uid = (user_id or "").strip()
    vid = (video_id or "").strip()
    if not uid or not vid:
        return 0
    label = canonical_subject(subject, exam_target)
    watch = (video_url or "").strip()
    ensure_session(
        db,
        user_id=uid,
        subject=label,
        video_id=vid,
        video_url=watch,
        label=session_label,
    )
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
    else:
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
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
    sessions = list_sessions(db, uid, subject=subject, exam_target=exam_target)
    label_map = _label_map(db, uid)
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
        public = _to_public(row, label_map)
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
        "sessions": sessions,
        "notes": notes,
        "questions": questions,
    }


def _to_public(
    row: SavedNotebookItem,
    label_map: dict[tuple[str, str], str] | None = None,
) -> dict | None:
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
    created = row.created_at.isoformat() if row.created_at else None
    session_label = ""
    if label_map is not None:
        session_label = label_map.get((row.subject or "Genel", row.video_id or ""), "")
    return {
        **payload,
        "saved_id": row.id,
        "subject": row.subject,
        "video_id": row.video_id or "",
        "session_label": session_label,
        "video_url": watch,
        "created_at": created,
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
