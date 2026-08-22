"""Video analiz işleri: ilk 5 dakikayı hemen ver, kalan dilimleri arka planda ekle."""

from __future__ import annotations

import logging
import threading
import uuid
from typing import Any

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_JOBS: dict[str, dict[str, Any]] = {}


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
