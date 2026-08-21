"""Güçlü bir modelin ürettiği yanıtları eğitim verisi olarak biriktirir.

Amaç damıtma (distillation): bulut modeli çalışırken her istek/yanıt çifti kaydedilir,
sonra bu çiftlerle küçük bir açık model kendi KPSS modelimiz olacak şekilde eğitilir.
Kayıt yalnızca CAPTURE_TRAINING_DATA=true iken açılır.
"""

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

TRAIN_DIR = Path(__file__).resolve().parents[3] / "training" / "data" / "raw"
_lock = threading.Lock()


def record(
    task: str,
    system_prompt: str,
    user_prompt: str,
    answer: dict,
) -> None:
    if not settings.capture_training_data:
        return
    try:
        with _lock:
            TRAIN_DIR.mkdir(parents=True, exist_ok=True)
            path = TRAIN_DIR / f"{datetime.now(timezone.utc):%Y-%m-%d}.jsonl"
            row = {
                "task": task,
                "provider": settings.llm_provider,
                "model": settings.active_model,
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "system": system_prompt,
                "user": user_prompt,
                "assistant": json.dumps(answer, ensure_ascii=False),
            }
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError as exc:
        logger.warning("Eğitim verisi yazılamadı: %s", exc)
