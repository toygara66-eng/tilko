"""Video analiz işleri: ilk 5 dakikayı hemen ver, kalan dilimleri arka planda ekle."""

from __future__ import annotations

import logging
import threading
import uuid
from typing import Any

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_JOBS: dict[str, dict[str, Any]] = {}
MAX_RUNNING_JOBS = 16


def create_job(
    *,
    user_id: str,
    video_id: str,
    video_url: str,
    subject: str | None,
    chunks_total: int,
    overlay: dict,
) -> str:
    job_id = uuid.uuid4().hex
    with _lock:
        _JOBS[job_id] = {
            "id": job_id,
            "user_id": user_id,
            "video_id": video_id,
            "video_url": video_url,
            "subject": subject or "",
            "status": "running",
            "chunks_done": 0,
            "chunks_total": max(1, chunks_total),
            "notes": [],
            "questions": [],
            "teacher_persona": {"catchphrases": [], "tone": "öğretici, net"},
            "error": "",
            "overlay": overlay,
        }
    return job_id


def running_count() -> int:
    with _lock:
        return sum(1 for job in _JOBS.values() if job.get("status") == "running")


def find_running(video_id: str, subject: str | None) -> dict[str, Any] | None:
    wanted = (subject or "").strip()
    with _lock:
        for job in _JOBS.values():
            if job.get("status") != "running":
                continue
            if job.get("video_id") != video_id:
                continue
            if (job.get("subject") or "").strip() != wanted:
                continue
            return dict(job)
    return None


def ensure_capacity() -> None:
    from app.services.scale import ServiceBusyError

    if running_count() >= MAX_RUNNING_JOBS:
        raise ServiceBusyError(
            "Sunucu meşgul. Aynı videoyu izleyenler sıraya alındı; 15 saniye sonra dene."
        )


def snapshot(job_id: str) -> dict[str, Any] | None:
    with _lock:
        job = _JOBS.get(job_id)
        if not job:
            return None
        return dict(job)


def set_progress(
    job_id: str,
    *,
    notes: list,
    questions: list,
    persona: dict,
    chunks_done: int,
    status: str | None = None,
    chunks_total: int | None = None,
    overlay: dict | None = None,
) -> None:
    with _lock:
        job = _JOBS.get(job_id)
        if not job:
            return
        job["notes"] = notes
        job["questions"] = questions
        job["teacher_persona"] = persona or job["teacher_persona"]
        job["chunks_done"] = chunks_done
        if status:
            job["status"] = status
        if chunks_total is not None:
            job["chunks_total"] = max(1, chunks_total)
        if overlay is not None:
            job["overlay"] = overlay


def finish(job_id: str, status: str = "done", error: str = "") -> None:
    with _lock:
        job = _JOBS.get(job_id)
        if not job:
            return
        job["status"] = status
        job["error"] = error
        if status == "done":
            job["chunks_done"] = job["chunks_total"]


def track_follower(job_id: str, user_id: str, charge_kind: str) -> None:
    """Paylaşılan işe katılan kullanıcı — iş bitince confirm/refund."""
    uid = (user_id or "").strip()
    if not uid or not job_id:
        return
    with _lock:
        job = _JOBS.get(job_id)
        if not job:
            return
        bag = job.setdefault("followers", {})
        if uid in bag:
            return
        bag[uid] = {"charge_kind": charge_kind or "trial", "settled": False}


def take_unsettled_followers(job_id: str) -> list[tuple[str, str]]:
    with _lock:
        job = _JOBS.get(job_id)
        if not job:
            return []
        out: list[tuple[str, str]] = []
        for uid, meta in list((job.get("followers") or {}).items()):
            if meta.get("settled"):
                continue
            meta["settled"] = True
            out.append((uid, str(meta.get("charge_kind") or "trial")))
        return out


def mark_follower_settled(job_id: str, user_id: str) -> str | None:
    """Takipçiyi settled yap; charge_kind döner (yoksa None)."""
    uid = (user_id or "").strip()
    with _lock:
        job = _JOBS.get(job_id)
        if not job:
            return None
        meta = (job.get("followers") or {}).get(uid)
        if not meta or meta.get("settled"):
            return None
        meta["settled"] = True
        return str(meta.get("charge_kind") or "trial")
