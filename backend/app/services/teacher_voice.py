"""Kullanıcının en çok izlediği hoca üslubu — bildirim kişiselleştirme."""

from __future__ import annotations

import json
import re
from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.models import NotebookSession, SavedNotebookItem
from app.services.ai_engine import merge_personas

_STOP = {
    "konu",
    "anlatım",
    "anlatimi",
    "anlatımı",
    "ders",
    "not",
    "notları",
    "notlari",
    "pdf",
    "soru",
    "sorular",
    "video",
    "özet",
    "ozet",
    "tekrar",
    "kamp",
    "canlı",
    "canli",
    "ücretsiz",
    "ucretsiz",
    "kpss",
    "yks",
    "öabt",
    "oabt",
    "lgs",
    "türkçe",
    "turkce",
    "tarih",
    "coğrafya",
    "cografya",
    "matematik",
    "vatandaşlık",
    "vatandaslik",
    "genel",
    "isimsiz",
    "seti",
    "hoca",
    "hocası",
    "hocasi",
}


def _fold(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").casefold()).strip()


def guess_teacher_name(label: str) -> str:
    """Oturum etiketinden hoca adı: 'Türkçe · Aker Kartal' → Aker Kartal."""
    raw = (label or "").strip()
    if not raw:
        return ""
    part = raw.split("·")[-1].split("|")[-1].strip()
    words = [w for w in re.split(r"[\s,/|\-]+", part) if w]
    kept: list[str] = []
    for w in words:
        key = _fold(w).strip(".,;:!?()[]\"'")
        if len(key) < 2 or key in _STOP:
            if kept:
                break
            continue
        if key.isdigit():
            continue
        # Tarih damgası 17.09.2026
        if re.match(r"^\d{1,2}\.\d{1,2}\.\d{2,4}$", key):
            continue
        kept.append(w.strip(".,;:!?()[]\"'"))
        if len(kept) >= 3:
            break
    name = " ".join(kept).strip()
    if len(name) < 3:
        return ""
    return name[:48]


def favorite_teacher(db: Session, user_id: str) -> dict:
    """En sık dönüştürülen hoca + catchphrase/tone."""
    uid = (user_id or "").strip()
    empty = {
        "name": "",
        "catchphrases": [],
        "tone": "öğretici, net",
        "sessions": 0,
        "notes": 0,
    }
    if not uid:
        return empty

    name_scores: Counter[str] = Counter()
    name_examples: dict[str, str] = {}

    # Not sayılarına göre oturum etiketlerinden puan
    count_q = (
        select(
            SavedNotebookItem.subject,
            SavedNotebookItem.video_id,
            func.count(SavedNotebookItem.id),
        )
        .where(
            SavedNotebookItem.user_id == uid,
            SavedNotebookItem.kind == "note",
            SavedNotebookItem.video_id != "",
        )
        .group_by(SavedNotebookItem.subject, SavedNotebookItem.video_id)
    )
    tallies = {
        (subj or "Genel", vid or ""): int(n or 0)
        for subj, vid, n in db.execute(count_q).all()
        if vid
    }

    sessions = list(
        db.scalars(select(NotebookSession).where(NotebookSession.user_id == uid)).all()
    )
    for row in sessions:
        guessed = guess_teacher_name(row.label or "")
        if not guessed:
            continue
        key = _fold(guessed)
        weight = max(1, tallies.get((row.subject or "Genel", row.video_id or ""), 1))
        name_scores[key] += weight
        name_examples.setdefault(key, guessed)

    personas_raw: list[object] = []
    q_rows = db.scalars(
        select(SavedNotebookItem)
        .where(
            SavedNotebookItem.user_id == uid,
            SavedNotebookItem.kind == "question",
        )
        .order_by(SavedNotebookItem.id.desc())
        .limit(100)
    ).all()
    for row in q_rows:
        try:
            payload = json.loads(row.payload_json or "{}")
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        persona = payload.get("teacher_persona")
        if not persona:
            continue
        personas_raw.append(persona)
        if isinstance(persona, dict):
            pname = str(persona.get("name") or "").strip()
            if len(pname) >= 3:
                key = _fold(pname)
                name_scores[key] += 2
                name_examples.setdefault(key, pname[:48])

    merged = merge_personas(personas_raw)
    # merge_personas name taşırsa skorla birleştir
    if merged.name:
        key = _fold(merged.name)
        if key not in name_scores:
            name_scores[key] += 1
        name_examples.setdefault(key, merged.name[:48])

    top_key = name_scores.most_common(1)[0][0] if name_scores else ""
    name = name_examples.get(top_key, "") if top_key else (merged.name or "")
    return {
        "name": name,
        "catchphrases": list(merged.catchphrases or [])[:10],
        "tone": merged.tone or "öğretici, net",
        "sessions": len(name_scores),
        "notes": int(name_scores[top_key]) if top_key else 0,
    }


def favorite_teachers_batch(db: Session, user_ids: list[str]) -> dict[str, dict]:
    """Admin listesi için: user_id → {name, notes} (hafif batch)."""
    ids = [u.strip() for u in user_ids if (u or "").strip()]
    empty = {"name": "", "notes": 0, "tone": ""}
    out: dict[str, dict] = {uid: dict(empty) for uid in ids}
    if not ids:
        return out

    scores: dict[str, Counter[str]] = {uid: Counter() for uid in ids}
    examples: dict[str, dict[str, str]] = {uid: {} for uid in ids}

    count_q = (
        select(
            SavedNotebookItem.user_id,
            SavedNotebookItem.subject,
            SavedNotebookItem.video_id,
            func.count(SavedNotebookItem.id),
        )
        .where(
            SavedNotebookItem.user_id.in_(ids),
            SavedNotebookItem.kind == "note",
            SavedNotebookItem.video_id != "",
        )
        .group_by(
            SavedNotebookItem.user_id,
            SavedNotebookItem.subject,
            SavedNotebookItem.video_id,
        )
    )
    tallies: dict[tuple[str, str, str], int] = {}
    for uid, subj, vid, n in db.execute(count_q).all():
        if not uid or not vid:
            continue
        tallies[(str(uid), subj or "Genel", str(vid))] = int(n or 0)

    sessions = db.scalars(
        select(NotebookSession).where(NotebookSession.user_id.in_(ids))
    ).all()
    for row in sessions:
        uid = (row.user_id or "").strip()
        if uid not in scores:
            continue
        guessed = guess_teacher_name(row.label or "")
        if not guessed:
            continue
        key = _fold(guessed)
        weight = max(
            1,
            tallies.get((uid, row.subject or "Genel", row.video_id or ""), 1),
        )
        scores[uid][key] += weight
        examples[uid].setdefault(key, guessed)

    # Son sorulardan persona.name (kullanıcı başına ~40 satır yeter)
    q_rows = db.scalars(
        select(SavedNotebookItem)
        .where(
            SavedNotebookItem.user_id.in_(ids),
            SavedNotebookItem.kind == "question",
        )
        .order_by(SavedNotebookItem.id.desc())
        .limit(max(40 * len(ids), 80))
    ).all()
    per_user_seen: Counter[str] = Counter()
    for row in q_rows:
        uid = (row.user_id or "").strip()
        if uid not in scores or per_user_seen[uid] >= 40:
            continue
        per_user_seen[uid] += 1
        try:
            payload = json.loads(row.payload_json or "{}")
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        persona = payload.get("teacher_persona")
        if not isinstance(persona, dict):
            continue
        pname = str(persona.get("name") or "").strip()
        if len(pname) < 3:
            continue
        key = _fold(pname)
        scores[uid][key] += 2
        examples[uid].setdefault(key, pname[:48])

    for uid in ids:
        top = scores[uid].most_common(1)
        if not top:
            continue
        top_key, top_n = top[0]
        out[uid] = {
            "name": examples[uid].get(top_key, ""),
            "notes": int(top_n),
            "tone": "",
        }
    return out
