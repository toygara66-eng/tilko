import hashlib
import json
import logging
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache"


def build_key(
    video_id: str,
    subject: str | None,
    question_count: int,
    exam_target: str | None = None,
    subject_type: str | None = None,
    is_yks_fen_question: bool = False,
    style_revision: int = 0,
) -> str:
    raw = (
        f"{video_id}|{subject or ''}|{question_count}|{exam_target or ''}"
        f"|{subject_type or ''}|{int(bool(is_yks_fen_question))}|r{style_revision}"
        f"|{settings.llm_provider}|{settings.active_model}|fullspan1"
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def _path(key: str) -> Path:
    return CACHE_DIR / f"{key}.json"


def load(key: str) -> dict | None:
    path = _path(key)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Önbellek okunamadı (%s): %s", path.name, exc)
        return None


def find_cached(video_id: str, subject: str | None) -> dict | None:
    """Soru sayısı değişse bile aynı video+ders kaydını kullan."""
    if not CACHE_DIR.exists():
        return None
    wanted_subject = (subject or "").strip()
    for path in CACHE_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("video_id") != video_id:
            continue
        if (str(data.get("subject") or "").strip()) != wanted_subject:
            continue
        if data.get("analyze_span") != "full":
            continue
        if data.get("notes") and data.get("questions"):
            return data
    return None


def save(key: str, payload: dict) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _path(key).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError as exc:
        logger.warning("Önbellek yazılamadı: %s", exc)
