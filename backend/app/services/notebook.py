"""Analiz notları ve soruları ders ders birikir; kaybolmaz."""

from __future__ import annotations

import hashlib
import json
import logging
import re

from sqlalchemy import func, or_, select
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
            current = (row.label or "").strip()
            # Kullanıcı özel isim verdiyse üzerine yazma; generic/boş ise hoca adını işle
            generic = (
                not current
                or "notlar" in current.casefold()
                or bool(re.search(r"\d{1,2}\.\d{1,2}\.\d{2,4}", current))
            )
            if cleaned and generic:
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
    """Oturum listesi — tüm not satırlarını çekmeden GROUP BY ile sayar."""
    uid = (user_id or "").strip()
    want = ""
    if (subject or "").strip():
        want = canonical_subject(subject, exam_target)

    count_q = (
        select(
            SavedNotebookItem.subject,
            SavedNotebookItem.video_id,
            SavedNotebookItem.kind,
            func.count(SavedNotebookItem.id),
            func.max(SavedNotebookItem.video_url),
        )
        .where(SavedNotebookItem.user_id == uid)
        .where(SavedNotebookItem.video_id != "")
        .group_by(
            SavedNotebookItem.subject,
            SavedNotebookItem.video_id,
            SavedNotebookItem.kind,
        )
    )
    if want:
        count_q = count_q.where(SavedNotebookItem.subject == want)

    tallies: dict[tuple[str, str], dict[str, int]] = {}
    urls: dict[tuple[str, str], str] = {}
    for subj, vid, kind, count, url in db.execute(count_q).all():
        key = (subj or "Genel", vid or "")
        if not key[1]:
            continue
        slot = tallies.setdefault(key, {"note_count": 0, "question_count": 0})
        if kind == "question":
            slot["question_count"] = int(count)
        else:
            slot["note_count"] = int(count)
        if url and key not in urls:
            urls[key] = str(url)

    if not tallies:
        return []

    session_q = select(NotebookSession).where(NotebookSession.user_id == uid)
    if want:
        session_q = session_q.where(NotebookSession.subject == want)
    session_map = {
        (r.subject or "Genel", r.video_id or ""): r
        for r in db.scalars(session_q).all()
        if r.video_id
    }

    dirty = False
    for key in tallies:
        if key in session_map:
            continue
        created = ensure_session(
            db,
            user_id=uid,
            subject=key[0],
            video_id=key[1],
            video_url=urls.get(key, ""),
        )
        if created:
            session_map[key] = created
            dirty = True
    if dirty:
        try:
            db.commit()
        except IntegrityError:
            db.rollback()

    out: list[dict] = []
    for key, counts in tallies.items():
        if not (counts["note_count"] or counts["question_count"]):
            continue
        row = session_map.get(key)
        pub = (
            _session_public(row)
            if row
            else {
                "id": 0,
                "subject": key[0],
                "video_id": key[1],
                "video_url": urls.get(key, ""),
                "label": f"{key[0]} notları",
                "created_at": None,
                "updated_at": None,
            }
        )
        pub.update(counts)
        out.append(pub)

    out.sort(
        key=lambda item: (
            item.get("updated_at") or item.get("created_at") or "",
            item.get("id") or 0,
        ),
        reverse=True,
    )
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
    """Türkçe destekli düzenli PDF (fpdf2)."""
    from fpdf import FPDF

    try:
        from fpdf.enums import XPos, YPos
    except ImportError:  # eski fpdf2
        XPos = YPos = None  # type: ignore[misc, assignment]

    regular, bold = _pdf_font_paths()
    pdf = FPDF(unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.set_margins(16, 16, 16)
    pdf.add_page()
    pdf.add_font("TilkoSans", "", regular)
    pdf.add_font("TilkoSans", "B", bold)
    usable = float(pdf.epw)  # etkili yazı genişliği

    def _clean(text: object) -> str:
        raw = str(text or "")
        # Kontrol karakterleri / garip boşluklar satırı bozmasın
        raw = raw.replace("\r\n", "\n").replace("\r", "\n")
        raw = "".join(ch if (ch == "\n" or ord(ch) >= 32) else " " for ch in raw)
        # Çok uzun tek kelime taşmasın
        parts: list[str] = []
        for word in raw.split(" "):
            if len(word) <= 48:
                parts.append(word)
                continue
            for i in range(0, len(word), 48):
                parts.append(word[i : i + 48])
        return " ".join(parts).strip()

    def write(text: object, *, weight: str = "", size: int = 11, gap: float = 1.5) -> None:
        body = _clean(text)
        if not body:
            return
        pdf.set_font("TilkoSans", weight, size)
        pdf.set_x(pdf.l_margin)
        line_h = max(5.0, size * 0.55)
        kwargs: dict = {}
        if XPos is not None and YPos is not None:
            kwargs["new_x"] = XPos.LMARGIN
            kwargs["new_y"] = YPos.NEXT
        pdf.multi_cell(usable, line_h, body, **kwargs)
        if gap:
            pdf.ln(gap)

    write("TİLKO — Ders Notları", weight="B", size=16, gap=2)
    write(f"{_clean(subject)} · {_clean(label)}", weight="B", size=12, gap=4)

    if not notes:
        write("Bu sette henüz not yok.")
    for index, note in enumerate(notes, start=1):
        title = _clean(note.get("title") or f"Not {index}")
        write(f"{index}. {title}", weight="B", size=12, gap=1)
        detail = _clean(
            note.get("text")
            or note.get("detail")
            or note.get("body")
            or note.get("content")
            or ""
        )
        if detail:
            write(detail, size=10, gap=1)
        points = note.get("key_points") or note.get("bullets") or []
        if isinstance(points, list):
            for point in points:
                line = _clean(point)
                if line:
                    write(f"- {line}", size=10, gap=0.5)
        tip = _clean(note.get("exam_tip") or "")
        if tip:
            write(f"Tuzak: {tip}", size=10, gap=0.5)
        mnemonic = _clean(note.get("mnemonic") or "")
        if mnemonic:
            write(f"Hafıza: {mnemonic}", size=10, gap=0.5)
        pdf.ln(3)

    extra_q = questions or []
    if extra_q:
        pdf.add_page()
        write("Soru bankası", weight="B", size=14, gap=2)
        for index, item in enumerate(extra_q, start=1):
            write(f"S{index}. {_clean(item.get('text') or '')}", weight="B", size=11, gap=1)
            options = item.get("options") or {}
            if isinstance(options, dict):
                for letter, opt in options.items():
                    mark = (
                        " (doğru)"
                        if str(letter) == str(item.get("correct") or "")
                        else ""
                    )
                    write(f"{letter}) {_clean(opt)}{mark}", size=10, gap=0.4)
            expl = _clean(item.get("explanation") or "")
            if expl:
                write(f"Açıklama: {expl}", size=9, gap=0.5)
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
    summary: bool = False,
    video_id: str | None = None,
    search: str | None = None,
) -> dict:
    uid = (user_id or "").strip()
    needle = (search or "").strip()
    if needle:
        return search_items(
            db,
            uid,
            query=needle,
            subject=subject,
            exam_target=exam_target,
        )

    counts = subject_counts(db, uid)
    sessions = list_sessions(db, uid, subject=subject, exam_target=exam_target)
    base = {
        "user_id": uid,
        "subject": (subject or "").strip() or None,
        "subjects": counts,
        "sessions": sessions,
        "notes": [],
        "questions": [],
    }
    vid = (video_id or "").strip()
    if summary or not vid:
        if not (subject or "").strip():
            base["sessions"] = []
        return base

    label_map = _label_map(db, uid)
    from app.services.question_safety import sanitize_options, scrub_premises_for_play

    def _fetch(subj_filter: str | None) -> list:
        query = (
            select(SavedNotebookItem)
            .where(SavedNotebookItem.user_id == uid)
            .where(SavedNotebookItem.video_id == vid)
        )
        if subj_filter:
            query = query.where(SavedNotebookItem.subject == subj_filter)
        query = query.order_by(
            SavedNotebookItem.timestamp.asc(),
            SavedNotebookItem.id.asc(),
        )
        return list(db.scalars(query).all())

    subj = ""
    if (subject or "").strip() and (subject or "").strip().casefold() not in {
        "tümü",
        "tumu",
        "all",
    }:
        subj = canonical_subject(subject, exam_target)

    # Önce subject+video; boşsa aynı video_id ile tüm dersler (eski kayıt uyumu).
    rows = _fetch(subj) if subj else _fetch(None)
    if not rows and subj:
        rows = _fetch(None)

    notes: list[dict] = []
    questions: list[dict] = []
    for row in rows:
        public = _to_public(row, label_map)
        if not public:
            continue
        if row.kind == "question":
            public["options"] = sanitize_options(public.get("options") or {})
            public["premises"] = scrub_premises_for_play(
                public.get("premises") or [], reveal=False
            )
            questions.append(public)
        else:
            notes.append(public)
    base["notes"] = notes
    base["questions"] = questions
    return base


def _search_tokens(query: str) -> list[str]:
    raw = (query or "").strip().casefold()
    if not raw:
        return []
    parts = []
    for p in re.split(r"\s+", raw):
        if not p:
            continue
        # "7", "I", "II" gibi kısa ama anlamlı tokenlar
        if len(p) >= 2 or p.isdigit() or re.fullmatch(r"[ivxlcdm]+", p):
            parts.append(p)
    if not parts and len(raw) >= 2:
        return [raw]
    return parts[:8]


def _note_search_blob(public: dict) -> str:
    bits = [
        str(public.get("title") or ""),
        str(public.get("text") or ""),
        str(public.get("detail") or ""),
        str(public.get("mnemonic") or ""),
        str(public.get("exam_tip") or ""),
        str(public.get("subject") or ""),
        str(public.get("session_label") or ""),
        " ".join(str(p) for p in (public.get("key_points") or [])),
    ]
    return " ".join(bits).casefold()


def search_items(
    db: Session,
    user_id: str,
    *,
    query: str,
    subject: str | None = None,
    exam_target: str | None = None,
    limit: int = 60,
) -> dict:
    """Başlık / metin / maddelerde kelime veya cümle arar."""
    uid = (user_id or "").strip()
    tokens = _search_tokens(query)
    counts = subject_counts(db, uid)
    base = {
        "user_id": uid,
        "subject": (subject or "").strip() or None,
        "subjects": counts,
        "sessions": [],
        "notes": [],
        "questions": [],
    }
    if not uid or not tokens:
        return base

    q = (
        select(SavedNotebookItem)
        .where(SavedNotebookItem.user_id == uid)
        .where(SavedNotebookItem.kind == "note")
        .order_by(SavedNotebookItem.id.desc())
        .limit(500)
    )
    want = ""
    if (subject or "").strip():
        want = canonical_subject(subject, exam_target)
        q = q.where(SavedNotebookItem.subject == want)

    # SQL ön süzgeç: ilk token title veya payload içinde
    first = tokens[0]
    like = f"%{first}%"
    q = q.where(
        or_(
            SavedNotebookItem.title.ilike(like),
            SavedNotebookItem.payload_json.ilike(like),
        )
    )

    label_map = _label_map(db, uid)
    scored: list[tuple[int, dict]] = []
    for row in db.scalars(q).all():
        public = _to_public(row, label_map)
        if not public:
            continue
        blob = _note_search_blob(public)
        if not all(tok in blob for tok in tokens):
            continue
        # Daha fazla eşleşen token / başlıkta geçen = üstte
        score = sum(
            3 if tok in (public.get("title") or "").casefold() else 1 for tok in tokens
        )
        if first in (public.get("title") or "").casefold():
            score += 5
        scored.append((score, public))

    scored.sort(key=lambda pair: (-pair[0], -(pair[1].get("saved_id") or 0)))
    base["notes"] = [item for _, item in scored[: max(1, min(limit, 80))]]
    return base


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
        persona = {"name": "", "catchphrases": [], "tone": "öğretici, net"}
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
            "name": str(persona.get("name") or ""),
            "catchphrases": list(persona.get("catchphrases") or []),
            "tone": str(persona.get("tone") or "öğretici, net"),
        },
    }
