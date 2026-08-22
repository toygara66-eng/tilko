import hashlib
import json
import logging
import threading
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

_index_lock = threading.Lock()
_index: dict[str, str] = {}


def _cache_dir() -> Path:
    raw = (settings.database_path or "").strip()
    if raw:
        return Path(raw).expanduser().resolve().parent / "analyze-cache"
    return Path(__file__).resolve().parents[2] / ".cache"


def _lookup_key(video_id: str, subject: str | None) -> str:
    return f"{video_id}|{(subject or '').strip()}"


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
    return _cache_dir() / f"{key}.json"


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
            _index[_lookup_key(video_id, data.get("subject"))] = key
    return data


def find_cached(video_id: str, subject: str | None) -> dict | None:
    """Soru sayısı değişse bile aynı video+ders kaydını kullan."""
    wanted = _lookup_key(video_id, subject)
    with _index_lock:
        key = _index.get(wanted)
    if key:
        hit = load(key)
        if (
            hit
            and hit.get("notes")
            and hit.get("questions")
            and str(hit.get("llm_model") or "") == str(settings.active_model or "")
        ):
            return hit
    cache_dir = _cache_dir()
    if not cache_dir.exists():
        return None
    wanted_subject = (subject or "").strip()
    for path in cache_dir.glob("*.json"):
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
        if str(data.get("llm_model") or "") != str(settings.active_model or ""):
            continue
        if data.get("notes") and data.get("questions"):
            with _index_lock:
                _index[wanted] = path.stem
            return data
    return None


def save(key: str, payload: dict) -> None:
    try:
        cache_dir = _cache_dir()
        cache_dir.mkdir(parents=True, exist_ok=True)
        _path(key).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        video_id = str(payload.get("video_id") or "")
        if video_id:
            with _index_lock:
                _index[_lookup_key(video_id, payload.get("subject"))] = key
    except OSError as exc:
        logger.warning("Önbellek yazılamadı: %s", exc)
