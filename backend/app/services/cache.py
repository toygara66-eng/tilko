"""Paylaşılan video analiz önbelleği: SQLite (kalıcı) + dosya yedek."""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

MIN_NOTES_DEPTH = 6

_index_lock = threading.Lock()
_index: dict[str, str] = {}


def _cache_dir() -> Path:
    raw = (settings.database_path or "").strip()
    if raw:
        return Path(raw).expanduser().resolve().parent / "analyze-cache"
    return Path(__file__).resolve().parents[2] / ".cache"


def _lookup_key(
    video_id: str,
    subject: str | None,
    exam_target: str | None = None,
    focus_bucket: int = 0,
) -> str:
    return (
        f"{video_id}|{(subject or '').strip()}|{(exam_target or '').strip()}"
        f"|f{int(focus_bucket or 0)}"
    )


def build_key(
    video_id: str,
    subject: str | None,
    question_count: int,
    exam_target: str | None = None,
    subject_type: str | None = None,
    is_yks_fen_question: bool = False,
    style_revision: int = 0,
    focus_bucket: int = 0,
) -> str:
    raw = (
        f"{video_id}|{subject or ''}|{question_count}|{exam_target or ''}"
        f"|{subject_type or ''}|{int(bool(is_yks_fen_question))}|r{style_revision}"
        f"|f{int(focus_bucket or 0)}"
        f"|{settings.llm_provider}|{settings.active_model}|examready1|ndepth{MIN_NOTES_DEPTH}"
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def _path(key: str) -> Path:
    return _cache_dir() / f"{key}.json"


def _usable(data: dict | None, *, focus_bucket: int, exam_target: str | None) -> bool:
    if not data:
        return False
    notes = data.get("notes") or []
    questions = data.get("questions") or []
    if not notes:
        return False
    # Soru yoksa bile en az 3 not varsa paylaş (LLM maliyeti bitmesin).
    if not questions and len(notes) < 3:
        return False
    if str(data.get("llm_model") or "") != str(settings.active_model or ""):
        return False
    if int(data.get("notes_depth") or 0) < MIN_NOTES_DEPTH:
        return False
    if int(data.get("focus_bucket") or 0) != int(focus_bucket or 0):
        return False
    if str(data.get("exam_target") or "").strip() != (exam_target or "").strip():
        return False
    return True


def _bump_hit(lookup: str) -> None:
    try:
        from app.database.models import AnalyzeCache
        from app.database.session import SessionLocal

        db = SessionLocal()
        try:
            row = (
                db.query(AnalyzeCache)
                .filter(AnalyzeCache.lookup_key == lookup)
                .one_or_none()
            )
            if row:
                row.hit_count = int(row.hit_count or 0) + 1
                db.commit()
        finally:
            db.close()
    except Exception:
        logger.debug("Önbellek hit sayacı atlandı", exc_info=True)


def _load_db(lookup: str) -> dict | None:
    try:
        from app.database.models import AnalyzeCache
        from app.database.session import SessionLocal

        db = SessionLocal()
        try:
            row = (
                db.query(AnalyzeCache)
                .filter(AnalyzeCache.lookup_key == lookup)
                .one_or_none()
            )
            if not row or not row.payload_json:
                return None
            return json.loads(row.payload_json)
        finally:
            db.close()
    except Exception as exc:
        logger.warning("DB önbellek okunamadı: %s", exc)
        return None


def _save_db(lookup: str, payload: dict) -> None:
    try:
        from app.database.models import AnalyzeCache
        from app.database.session import SessionLocal

        notes = payload.get("notes") or []
        questions = payload.get("questions") or []
        db = SessionLocal()
        try:
            row = (
                db.query(AnalyzeCache)
                .filter(AnalyzeCache.lookup_key == lookup)
                .one_or_none()
            )
            if row is None:
                row = AnalyzeCache(lookup_key=lookup)
                db.add(row)
            row.video_id = str(payload.get("video_id") or "")
            row.subject = str(payload.get("subject") or "")
            row.exam_target = str(payload.get("exam_target") or "")
            row.focus_bucket = int(payload.get("focus_bucket") or 0)
            row.llm_model = str(payload.get("llm_model") or settings.active_model or "")
            row.notes_depth = int(payload.get("notes_depth") or MIN_NOTES_DEPTH)
            row.note_count = len(notes)
            row.question_count = len(questions)
            row.payload_json = json.dumps(payload, ensure_ascii=False)
            db.commit()
        finally:
            db.close()
    except Exception as exc:
        logger.warning("DB önbellek yazılamadı: %s", exc)


def load(key: str) -> dict | None:
    path = _path(key)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Önbellek okunamadı (%s): %s", path.name, exc)
        return None
    video_id = str(data.get("video_id") or "")
    if video_id:
        with _index_lock:
            _index[
                _lookup_key(
                    video_id,
                    data.get("subject"),
                    data.get("exam_target"),
                    int(data.get("focus_bucket") or 0),
                )
            ] = key
    return data


def find_cached(
    video_id: str,
    subject: str | None,
    exam_target: str | None = None,
    focus_bucket: int = 0,
) -> dict | None:
    """Aynı video+ders+sınav+odak için kayıtlı analizi döndür (LLM yok)."""
    bucket = int(focus_bucket or 0)
    wanted = _lookup_key(video_id, subject, exam_target, bucket)

    db_hit = _load_db(wanted)
    if _usable(db_hit, focus_bucket=bucket, exam_target=exam_target):
        assert db_hit is not None
        _bump_hit(wanted)
        logger.info(
            "Analiz önbellek isabeti (DB) %s not=%s soru=%s",
            video_id,
            len(db_hit.get("notes") or []),
            len(db_hit.get("questions") or []),
        )
        return db_hit

    with _index_lock:
        key = _index.get(wanted)
    if key:
        hit = load(key)
        if _usable(hit, focus_bucket=bucket, exam_target=exam_target):
            assert hit is not None
            _save_db(wanted, hit)
            _bump_hit(wanted)
            return hit

    cache_dir = _cache_dir()
    if not cache_dir.exists():
        return None
    wanted_subject = (subject or "").strip()
    wanted_exam = (exam_target or "").strip()
    for path in cache_dir.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("video_id") != video_id:
            continue
        if (str(data.get("subject") or "").strip()) != wanted_subject:
            continue
        if not _usable(data, focus_bucket=bucket, exam_target=wanted_exam):
            continue
        with _index_lock:
            _index[wanted] = path.stem
        _save_db(wanted, data)
        _bump_hit(wanted)
        logger.info("Analiz önbellek isabeti (dosya→DB) %s", video_id)
        return data
    return None


def save(key: str, payload: dict) -> None:
    """Sonucu dosyaya ve SQLite'a yazar; sonraki kullanıcılar LLM'siz alır."""
    notes = payload.get("notes") or []
    if not notes:
        return
    payload = dict(payload)
    payload.setdefault("analyze_span", "full")
    payload.setdefault("llm_model", settings.active_model)
    payload.setdefault("notes_depth", MIN_NOTES_DEPTH)
    payload.setdefault("cached", False)

    lookup = _lookup_key(
        str(payload.get("video_id") or ""),
        payload.get("subject"),
        payload.get("exam_target"),
        int(payload.get("focus_bucket") or 0),
    )
    _save_db(lookup, payload)

    try:
        cache_dir = _cache_dir()
        cache_dir.mkdir(parents=True, exist_ok=True)
        _path(key).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        video_id = str(payload.get("video_id") or "")
        if video_id:
            with _index_lock:
                _index[lookup] = key
        logger.info(
            "Analiz önbelleğe alındı %s not=%s soru=%s",
            video_id,
            len(notes),
            len(payload.get("questions") or []),
        )
    except OSError as exc:
        logger.warning("Dosya önbellek yazılamadı (DB yazıldı): %s", exc)
