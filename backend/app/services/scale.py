"""Çok kullanıcılı analiz: LLM kuyruğu, aynı video için tek iş, iş tavanı."""

from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)

LLM_SLOTS = 2
MAX_LLM_WAITERS = 48
LLM_QUEUE_WAIT = 80.0
MAX_RUNNING_JOBS = 16
WORK_WAIT = 90.0


class ServiceBusyError(RuntimeError):
    retry_after = 15


_llm_slots = threading.Semaphore(LLM_SLOTS)
_llm_waiters = 0
_llm_lock = threading.Lock()
_work_lock = threading.Lock()
_work_events: dict[str, threading.Event] = {}


def work_key(video_id: str, subject: str | None, focus_bucket: int = 0) -> str:
    return f"{video_id}|{(subject or '').strip().lower()}|f{int(focus_bucket or 0)}"


def acquire_llm_slot() -> None:
    """Aynı anda en fazla LLM_SLOTS model çağrısı; fazlası sırada bekler."""
    global _llm_waiters
    with _llm_lock:
        if _llm_waiters >= MAX_LLM_WAITERS:
            raise ServiceBusyError(
                "Şu an çok fazla analiz var. 15 saniye sonra tekrar dene."
            )
        _llm_waiters += 1
    try:
        if not _llm_slots.acquire(timeout=LLM_QUEUE_WAIT):
            raise ServiceBusyError(
                "Analiz kuyruğu dolu. Biraz bekleyip tekrar dene; üst üste basma."
            )
    finally:
        with _llm_lock:
            _llm_waiters = max(0, _llm_waiters - 1)


def release_llm_slot() -> None:
    _llm_slots.release()


def claim_work(
    video_id: str, subject: str | None, focus_bucket: int = 0
) -> bool:
    """True: sen LLM çalıştır. False: başka biri aynı videoyu çözüyor, bekle."""
    key = work_key(video_id, subject, focus_bucket)
    with _work_lock:
        if key in _work_events:
            return False
        _work_events[key] = threading.Event()
        return True


def wait_work(
    video_id: str,
    subject: str | None,
    timeout: float = WORK_WAIT,
    focus_bucket: int = 0,
) -> bool:
    key = work_key(video_id, subject, focus_bucket)
    with _work_lock:
        event = _work_events.get(key)
    if event is None:
        return True
    return event.wait(timeout)


def release_work(
    video_id: str, subject: str | None, focus_bucket: int = 0
) -> None:
    key = work_key(video_id, subject, focus_bucket)
    with _work_lock:
        event = _work_events.pop(key, None)
    if event is not None:
        event.set()
