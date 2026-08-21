"""OpenRouter sohbet çağrılarında usage bilgisini TokenUsageLogs'a yazar."""

from __future__ import annotations

import logging
from contextvars import ContextVar
from functools import wraps
from typing import Any, Callable, TypeVar

from app.config import settings

logger = logging.getLogger(__name__)

usage_task: ContextVar[str] = ContextVar("tilko_usage_task", default="genel")

F = TypeVar("F", bound=Callable[..., Any])


def persist_chat_usage(
    response: Any,
    *,
    task: str | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> None:
    usage = getattr(response, "usage", None)
    if usage is None:
        return
    provider = (provider or settings.llm_provider or "").strip().lower()
    if provider != "openrouter":
        return
    prompt = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion = int(getattr(usage, "completion_tokens", 0) or 0)
    total = int(getattr(usage, "total_tokens", 0) or (prompt + completion))
    model_name = (model or getattr(response, "model", "") or settings.openrouter_model or "")[:128]
    label = (task or usage_task.get() or "genel")[:64]
    try:
        from app.database.models import TokenUsageLog
        from app.database.session import SessionLocal

        db = SessionLocal()
        try:
            db.add(
                TokenUsageLog(
                    provider=provider,
                    model=model_name,
                    task=label,
                    prompt_tokens=prompt,
                    completion_tokens=completion,
                    total_tokens=total,
                )
            )
            db.commit()
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Jeton kullanımı yazılamadı: %s", exc)


def log_openrouter_usage(func: F) -> F:
    """OpenAI-uyumlu create çağrısının dönüşündeki usage alanını kaydeder."""

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any):
        response = func(*args, **kwargs)
        persist_chat_usage(response, task=usage_task.get())
        return response

    return wrapper  # type: ignore[return-value]
