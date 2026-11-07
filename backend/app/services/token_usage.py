"""Tüm LLM sağlayıcılarının (Gemini, Groq, Nebius, Cerebras, OpenRouter) usage bilgisini TokenUsageLogs'a yazar."""

from __future__ import annotations

import logging
from contextvars import ContextVar
from functools import wraps
from typing import Any, Callable, TypeVar

from app.config import settings

logger = logging.getLogger(__name__)

usage_task: ContextVar[str] = ContextVar("tilko_usage_task", default="genel")

F = TypeVar("F", bound=Callable[..., Any])


def infer_provider(model_name: str) -> str:
    """Yanıttaki model adından sağlayıcıyı tahmin eder (llm.py'ye bağımlılık yok)."""
    m = (model_name or "").lower()
    if "gemini" in m:
        return "gemini"
    if "llama" in m or "mixtral" in m:
        return "groq"
    if "qwen" in m:
        return "nebius"
    if "gemma" in m:
        return "cerebras"
    return (settings.llm_provider or "bilinmiyor").strip().lower() or "bilinmiyor"


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
    prompt = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion = int(getattr(usage, "completion_tokens", 0) or 0)
    total = int(getattr(usage, "total_tokens", 0) or (prompt + completion))
    if not (prompt or completion or total):
        return
    model_name = (model or getattr(response, "model", "") or "")[:128]
    provider = (provider or infer_provider(model_name)).strip().lower()
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


# Yaklaşık $/1M jeton (girdi, çıktı). Yalnızca tahmin içindir; ücretsiz katmanlar 0 sayılır.
_PRICE_PER_MTOK: dict[str, tuple[float, float]] = {
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.5-flash": (0.30, 2.50),
}


def _estimate_usd(model: str, prompt: int, completion: int) -> float:
    m = (model or "").lower().removeprefix("models/")
    price = None
    for key in sorted(_PRICE_PER_MTOK, key=len, reverse=True):
        if m.startswith(key):
            price = _PRICE_PER_MTOK[key]
            break
    if price is None:
        return 0.0
    return (prompt * price[0] + completion * price[1]) / 1_000_000


def summarize_usage(db: Any, *, days: int = 7) -> dict:
    """Son N günün jeton kullanımını sağlayıcı/model/görev bazında özetler."""
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import func, select

    from app.database.models import TokenUsageLog

    days = max(1, min(int(days), 90))
    since = datetime.now(timezone.utc) - timedelta(days=days)
    stmt = (
        select(
            TokenUsageLog.provider,
            TokenUsageLog.model,
            TokenUsageLog.task,
            func.count(TokenUsageLog.id),
            func.coalesce(func.sum(TokenUsageLog.prompt_tokens), 0),
            func.coalesce(func.sum(TokenUsageLog.completion_tokens), 0),
        )
        .where(TokenUsageLog.created_at >= since)
        .group_by(TokenUsageLog.provider, TokenUsageLog.model, TokenUsageLog.task)
    )
    rows = []
    total_usd = 0.0
    for provider, model, task, calls, prompt, completion in db.execute(stmt).all():
        usd = _estimate_usd(model, int(prompt), int(completion))
        total_usd += usd
        rows.append(
            {
                "provider": provider,
                "model": model,
                "task": task,
                "calls": int(calls),
                "prompt_tokens": int(prompt),
                "completion_tokens": int(completion),
                "avg_prompt_tokens": int(prompt) // max(int(calls), 1),
                "estimated_usd": round(usd, 4),
            }
        )
    rows.sort(key=lambda r: r["prompt_tokens"] + r["completion_tokens"], reverse=True)
    return {"days": days, "estimated_usd_total": round(total_usd, 4), "rows": rows}
