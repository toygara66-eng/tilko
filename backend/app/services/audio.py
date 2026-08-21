import logging
from pathlib import Path

import requests

from app.config import settings

logger = logging.getLogger(__name__)

ELEVEN_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
AUDIO_DIR = Path(__file__).resolve().parents[2] / "data" / "audio"


def synthesize_mp3(text: str, filename: str) -> Path:
    """OpenRouter özetini ElevenLabs ile MP3'e çevirir ve dosya yolunu döner."""
    if not settings.elevenlabs_api_key:
        raise RuntimeError(
            "ELEVENLABS_API_KEY tanımlı değil. elevenlabs.io/app/settings/api-keys "
            "adresinden anahtar alıp backend/.env dosyasına yazın."
        )
    if not text.strip():
        raise ValueError("Seslendirilecek metin boş.")

    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    path = AUDIO_DIR / filename
    url = ELEVEN_URL.format(voice_id=settings.elevenlabs_voice_id)
    response = requests.post(
        url,
        headers={
            "xi-api-key": settings.elevenlabs_api_key,
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
        },
        json={
            "text": text.strip(),
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.45, "similarity_boost": 0.75},
        },
        timeout=60,
    )
    if response.status_code == 401:
        raise RuntimeError("ElevenLabs anahtarı geçersiz veya süresi dolmuş.")
    if response.status_code >= 400:
        raise RuntimeError(
            f"ElevenLabs TTS başarısız ({response.status_code}): {response.text[:300]}"
        )
    path.write_bytes(response.content)
    logger.info("Koç sesi yazıldı: %s (%s bayt)", path.name, path.stat().st_size)
    return path
