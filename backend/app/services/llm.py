import json
import logging
import re
import threading
import time
import unicodedata
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
from math import ceil

import httpx
from openai import OpenAI

from app.config import settings
from app.services import capture
from app.services.token_usage import log_openrouter_usage, usage_task
from app.services.scale import (
    ServiceBusyError,
    acquire_llm_slot,
    release_llm_slot,
)
from app.prompts.kpss import (
    COACH_SYSTEM_PROMPT,
    NOTES_SYSTEM_PROMPT,
    build_coach_prompt,
    build_combined_analyze_prompt,
    build_notes_prompt,
    build_questions_prompt,
    questions_system_for,
)
from app.services.ai_engine import merge_personas, persona_system_block

logger = logging.getLogger(__name__)

JSON_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)
NON_WORD_RE = re.compile(r"[^a-z0-9]+")

CHAT_RETRIES = 1
RETRY_BACKOFF_SECONDS = (3,)
RATE_LIMIT_MAX_WAIT = 20
LLM_HTTP_TIMEOUT = httpx.Timeout(90.0, connect=12.0)
ANALYZE_HTTP_TIMEOUT = httpx.Timeout(50.0, connect=8.0)
ANALYZE_TASKS = frozenset({"analyze", "notes", "questions"})
ANALYZE_FAST_MODEL = "nvidia/nemotron-3-nano-30b-a3b:free"
GEMINI_CHAT_MODEL = "gemini-3.6-flash"
OPENROUTER_FREE_MODELS = (
    "nvidia/nemotron-3-nano-30b-a3b:free",
    "nvidia/nemotron-3.5-lightning:free",
    "nvidia/nemotron-nano-9b-v2:free",
    "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b-it:free",
)
_groq_gate = threading.Lock()
_groq_next_ok = 0.0
_provider_lock = threading.Lock()
_skip_openrouter = False
_openrouter_free_only = False
_skip_gemini = False
_chain_index = 0
_active_name = ""
RETRY_AFTER_RE = re.compile(
    r"try again in\s+(?:(?P<hours>\d+)h)?\s*(?:(?P<mins>\d+)m(?!s))?\s*(?P<num>[\d.]+)\s*(?P<unit>ms|s)",
    re.IGNORECASE,
)
TOPUP_ROUNDS = 0
OPTION_KEYS = ("A", "B", "C", "D", "E")
DIFFICULTY_ORDER = {"kolay": 0, "orta": 1, "zor": 2}


class FatalLLMError(RuntimeError):
    """Yeniden denemenin fayda etmeyeceği hatalar; akış hemen durdurulur."""


class QuotaExhaustedError(FatalLLMError):
    """Sağlayıcının kotası/kredisi bittiğinde yeniden denemek anlamsızdır."""


class ConfigurationError(FatalLLMError):
    """Eksik anahtar gibi ayar hataları; beklemek sonucu değiştirmez."""


def _ascii_header(value: str) -> str:
    """HTTP başlıkları yalnızca ASCII kabul eder; İ/Ş/Ğ kırılmasını önler."""
    folded = unicodedata.normalize("NFKD", value or "")
    clean = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return clean.encode("ascii", "ignore").decode("ascii") or "TILKO"


def _openai_client(**kwargs) -> OpenAI:
    kwargs.setdefault("max_retries", 0)
    kwargs.setdefault("timeout", LLM_HTTP_TIMEOUT)
    return OpenAI(**kwargs)


def _client() -> tuple[OpenAI, str]:
    # max_retries=0: SDK'nın kendi tekrarları da kotadan istek düşüyor, denemeyi biz yönetiyoruz.
    if settings.llm_provider == "gemini":
        if not settings.gemini_api_key:
            raise ConfigurationError(
                "GEMINI_API_KEY tanımlı değil. backend/.env dosyasını doldurun."
            )
        return (
            _openai_client(
                api_key=settings.gemini_api_key,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            ),
            _gemini_model_id(),
        )

    if settings.llm_provider == "huggingface":
        if not settings.hf_api_key:
            raise ConfigurationError(
                "HF_API_KEY tanımlı değil. huggingface.co/settings/tokens adresinden "
                "bir token alıp backend/.env dosyasına yazın."
            )
        return (
            _openai_client(api_key=settings.hf_api_key, base_url=settings.hf_base_url),
            settings.hf_model,
        )

    if settings.llm_provider == "groq":
        if not settings.groq_api_key:
            raise ConfigurationError(
                "GROQ_API_KEY tanımlı değil. console.groq.com/keys adresinden "
                "bir anahtar alıp backend/.env dosyasına yazın."
            )
        return (
            _openai_client(
                api_key=settings.groq_api_key,
                base_url=settings.groq_base_url,
            ),
            settings.groq_model,
        )

    if settings.llm_provider == "cerebras":
        pair = _cerebras_client(timeout=LLM_HTTP_TIMEOUT)
        if not pair:
            raise ConfigurationError(
                "CEREBRAS_API_KEY tanımlı değil. cloud.cerebras.ai adresinden "
                "ücretsiz anahtar al (kart istemez, günde ~1M jeton)."
            )
        return pair

    if settings.llm_provider == "openrouter":
        if _chain_index > 0:
            pair = _fast_analyze_client()
            if pair:
                return pair
        if not settings.openrouter_api_key:
            raise ConfigurationError(
                "OPENROUTER_API_KEY tanımlı değil. openrouter.ai/keys adresinden "
                "bir anahtar alıp backend/.env dosyasına yazın."
            )
        model = ANALYZE_FAST_MODEL
        return (
            _openai_client(
                api_key=settings.openrouter_api_key,
                base_url=settings.openrouter_base_url,
                default_headers={
                    "HTTP-Referer": "https://tilko.site",
                    "X-Title": _ascii_header("TILKO"),
                },
            ),
            model,
        )

    if not settings.openai_api_key:
        raise ConfigurationError(
            "OPENAI_API_KEY tanımlı değil. backend/.env dosyasını doldurun."
        )
    return _openai_client(api_key=settings.openai_api_key), settings.openai_model


def _is_gemini_quota_error(raw: str) -> bool:
    text = raw.lower()
    googleish = (
        "generativelanguage.googleapis.com" in text
        or "gemini" in text
        or "you exceeded your current quota" in text
        or "resource_exhausted" in text
    )
    return googleish and (
        "quota" in text or "resource_exhausted" in text or "429" in raw
    )


def _fatal_message(raw: str) -> str | None:
    """Yeniden denemenin fayda etmeyeceği kota ve izin hatalarını tanır."""
    text = raw.lower()
    if "inference providers" in text and "permission" in text:
        return (
            "Hugging Face token'ında 'Inference Providers' izni yok. "
            "huggingface.co/settings/tokens adresinde token'ı düzenleyip "
            "'Make calls to Inference Providers' kutusunu işaretleyin "
            "(veya Read yetkili klasik bir token oluşturun)."
        )
    if "depleted" in text and "credits" in text:
        return (
            "Hugging Face aylık ücretsiz kredin bitti. Seçenekler: backend/.env içinde "
            "LLM_PROVIDER=ollama yaparak yerel modele geç (ücretsiz, yavaş), "
            "LLM_PROVIDER=gemini yaz (günde 20 istek) veya HF PRO'ya abone ol."
        )
    if (
        "insufficient credits" in text
        or "requires at least" in text
        or (
            ("credit" in text or "balance" in text)
            and (
                settings.llm_provider == "openrouter"
                or "openrouter" in text
            )
        )
    ):
        if _chain_index > 0:
            return (
                "Ücretsiz yedekler de yanıt vermedi. Groq (console.groq.com) ve "
                "Cerebras (cloud.cerebras.ai, günde 1M jeton) anahtarlarını Render'a ekle."
            )
        return (
            "OpenRouter kredin bitmiş. Groq/Cerebras yedeğine geçiliyor."
        )
    if "tokens per day" in text or ("per day" in text and settings.llm_provider == "groq"):
        # Rolling TPD: 'try again in 5m' ise beklemek yeterli; saatlerceyse gerçekten bitti.
        wait = _retry_after(raw)
        if wait is None or wait >= RATE_LIMIT_MAX_WAIT:
            return (
                "Groq'un günlük ücretsiz jeton sınırı doldu (gpt-oss-120b için 200K/gün). "
                "Aynı gün devam için GROQ_MODEL=openai/gpt-oss-20b yaz (ayrı kota) "
                "veya LLM_PROVIDER=ollama ile yerel modele geç."
            )
    if "insufficient_quota" in text:
        return (
            "OpenAI hesabının kredisi bitmiş. backend/.env içinde LLM_PROVIDER=gemini "
            "yapabilir veya OpenAI faturalandırmasını açabilirsin."
        )
    if _is_gemini_quota_error(raw) or (
        "exceeded your current quota" in text
        or ("429" in raw and "quota" in text and "gemini" in text)
    ):
        if _groq_fast_client():
            return "Gemini ücretsiz kotası doldu; Groq yedeğine geçiliyor."
        return (
            "Gemini ücretsiz kotası doldu. Yarın tekrar dene."
        )
    if "perday" in text.replace(" ", "") or "requests per day" in text:
        return (
            "Gemini ücretsiz kotasının GÜNLÜK istek sınırı doldu. "
            "Groq yedeği varsa ona geçilir; yoksa yarın tekrar dene."
        )
    return None


def _oversized_request(raw: str) -> bool:
    """İstek dakikalık jeton tavanından büyükse beklemek boyutu küçültmez."""
    text = raw.lower()
    return "request too large" in text or "please reduce your message size" in text


def _retry_after(raw: str) -> float | None:
    """Sağlayıcı 'try again in 952.5ms' / '7.5s' / '1m7s' derse o kadar bekleriz."""
    match = RETRY_AFTER_RE.search(raw)
    if not match:
        return None
    hours = int(match.group("hours") or 0)
    minutes = int(match.group("mins") or 0)
    amount = float(match.group("num"))
    if match.group("unit").lower() == "ms":
        amount /= 1000
    return min(hours * 3600 + minutes * 60 + amount, RATE_LIMIT_MAX_WAIT)


def _as_dict(value: object) -> dict:
    """LLM bazen kökte dizi döner; çağrıların hepsi sözlük bekler."""
    if isinstance(value, dict):
        return value
    if not isinstance(value, list):
        return {}
    notes: list[dict] = []
    questions: list[dict] = []
    persona = None
    for item in value:
        if not isinstance(item, dict):
            continue
        if item.get("options") or item.get("correct"):
            questions.append(item)
        elif "catchphrases" in item or (
            "tone" in item and "title" not in item and "detail" not in item
        ):
            persona = item
        elif "notes" in item or "questions" in item:
            notes.extend(_dicts(item.get("notes")))
            questions.extend(_dicts(item.get("questions")))
            if persona is None and item.get("teacher_persona"):
                persona = item.get("teacher_persona")
        else:
            notes.append(item)
    out: dict = {}
    if notes:
        out["notes"] = notes
    if questions:
        out["questions"] = questions
    if persona is not None:
        out["teacher_persona"] = persona
    return out


def _dicts(value: object) -> list[dict]:
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


_TRAILING_COMMA_RE = re.compile(r",\s*(?=[}\]])")


def _message_text(message: object) -> str:
    content = getattr(message, "content", None)
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                parts.append(str(part.get("text") or ""))
            else:
                parts.append(str(part or ""))
        return " ".join(parts).strip()
    return str(content or "").strip()


def _close_truncated_json(text: str) -> str:
    blob = text.rstrip()
    in_str = False
    escape = False
    stack: list[str] = []
    for char in blob:
        if in_str:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_str = False
            continue
        if char == '"':
            in_str = True
        elif char == "{":
            stack.append("}")
        elif char == "[":
            stack.append("]")
        elif char in "}]" and stack:
            stack.pop()
    if in_str:
        blob += '"'
    blob += "".join(reversed(stack))
    return blob


def _loads_json_lenient(text: str):
    blobs = [text]
    cleaned = _TRAILING_COMMA_RE.sub("", text)
    if cleaned not in blobs:
        blobs.append(cleaned)
    closed = _close_truncated_json(cleaned)
    if closed not in blobs:
        blobs.append(closed)
    last_error: Exception | None = None
    for blob in blobs:
        try:
            return json.loads(blob)
        except json.JSONDecodeError as exc:
            last_error = exc
            try:
                parsed, _ = json.JSONDecoder().raw_decode(blob.lstrip())
                return parsed
            except json.JSONDecodeError as inner:
                last_error = inner
    if last_error:
        raise last_error
    raise json.JSONDecodeError("JSON yok", text, 0)


def _pick_note_field(item: dict, *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _coerce_notes(result: dict) -> list[dict]:
    raw = (
        _dicts(result.get("notes"))
        or _dicts(result.get("notlar"))
        or _dicts(result.get("study_notes"))
    )
    notes: list[dict] = []
    for item in raw:
        title = _pick_note_field(item, "title", "baslik", "başlık", "name", "konu")
        detail = _pick_note_field(
            item, "detail", "text", "detay", "icerik", "içerik", "aciklama", "açıklama"
        )
        if not title and not detail:
            continue
        notes.append(
            {
                **item,
                "title": title or detail[:48],
                "detail": detail or title,
            }
        )
    return notes


def _extract_json(raw: str) -> dict:
    text = raw.strip()
    fenced = JSON_FENCE_RE.search(text)
    if fenced:
        text = fenced.group(1).strip()
    try:
        parsed = _loads_json_lenient(text)
    except json.JSONDecodeError:
        stripped = text.lstrip()
        if stripped.startswith("["):
            start, end = text.find("["), text.rfind("]")
            parsed = _loads_json_lenient(text[start : end + 1] if end > start else stripped)
        else:
            start, end = text.find("{"), text.rfind("}")
            if start < 0:
                raise
            chunk = text[start : end + 1] if end > start else text[start:]
            parsed = _loads_json_lenient(chunk)
    data = _as_dict(parsed)
    if "notes" not in data and isinstance(parsed, dict):
        alt = parsed.get("notlar") or parsed.get("study_notes")
        if alt:
            data["notes"] = alt
    return data


def _chat_ollama(system_prompt: str, user_prompt: str, temperature: float) -> dict:
    """Yerel Ollama sunucusunu kendi API'siyle çağırır (bağlam boyutunu ayarlayabilmek için)."""
    url = f"{settings.ollama_base_url.rstrip('/')}/api/chat"
    payload = {
        "model": settings.ollama_model,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": temperature,
            "num_ctx": settings.ollama_num_ctx,
        },
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    try:
        response = httpx.post(url, json=payload, timeout=900)
    except httpx.RequestError as exc:
        raise RuntimeError(
            f"Yerel model sunucusuna ulaşılamadı ({url}). Ollama çalışıyor mu? "
            "Terminalde 'ollama serve' komutunu deneyin."
        ) from exc
    if response.status_code == 404:
        raise RuntimeError(
            f"Ollama '{settings.ollama_model}' modelini bulamadı. "
            f"Önce 'ollama pull {settings.ollama_model}' komutunu çalıştırın."
        )
    response.raise_for_status()
    return _extract_json(response.json().get("message", {}).get("content") or "{}")


def _is_timeout(exc: BaseException) -> bool:
    if isinstance(exc, (httpx.TimeoutException, TimeoutError)):
        return True
    name = type(exc).__name__.lower()
    if "timeout" in name:
        return True
    text = str(exc).lower()
    return "timed out" in text or "timeout" in text


def _reasoning_extra() -> dict:
    """gpt-oss varsayılan düşünme çabasıyla her not turunu dakikalarca uzatır."""
    if not settings.is_reasoning_model:
        return {}
    return {"reasoning": {"effort": "minimal", "exclude": True}}


def _gemini_model_id() -> str:
    return GEMINI_CHAT_MODEL


def _gemini_models_to_try() -> list[str]:
    return [GEMINI_CHAT_MODEL]


def _is_gemini_client(client: OpenAI) -> bool:
    base = str(getattr(client, "base_url", "") or "")
    return "generativelanguage.googleapis.com" in base


def _as_chat_response(text: str, model: str):
    message = SimpleNamespace(content=text)
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(choices=[choice], model=model, usage=None)


def _gemini_native_completion(
    messages: list[dict],
    temperature: float,
    json_mode: bool,
) -> object:
    key = (settings.gemini_api_key or "").strip()
    if not key:
        raise ConfigurationError("GEMINI_API_KEY tanımlı değil.")
    system = ""
    user_parts: list[str] = []
    for message in messages:
        role = str(message.get("role") or "")
        content = str(message.get("content") or "")
        if role == "system":
            system = content
        elif content:
            user_parts.append(content)
    user = "\n\n".join(user_parts).strip()
    last: Exception | None = None
    for name in _gemini_models_to_try():
        generation = {
            "temperature": temperature,
            "maxOutputTokens": 7000,
            "thinkingConfig": {"thinkingBudget": 0},
        }
        if json_mode:
            generation["responseMimeType"] = "application/json"
        payload: dict = {
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": generation,
        }
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{name}:generateContent"
        )
        try:
            response = httpx.post(
                url,
                headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                json=payload,
                timeout=ANALYZE_HTTP_TIMEOUT,
            )
        except Exception as exc:  # noqa: BLE001
            last = exc
            logger.warning("Gemini %s ağ hatası: %s", name, exc)
            continue
        if response.status_code == 400 and "thinking" in (response.text or "").lower():
            generation.pop("thinkingConfig", None)
            payload["generationConfig"] = generation
            try:
                response = httpx.post(
                    url,
                    headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                    json=payload,
                    timeout=ANALYZE_HTTP_TIMEOUT,
                )
            except Exception as exc:  # noqa: BLE001
                last = exc
                continue
        if response.status_code == 404:
            raise ConfigurationError(
                "GEMINI_MODEL=gemini-3.6-flash bu anahtarda yok. "
                "Google AI Studio'da 3.6 Flash'i aç veya anahtarı yenile."
            )
        if response.status_code == 429:
            raise RuntimeError(
                f"{name}: 429 You exceeded your current quota. {response.text[:200]}"
            )
        if not response.is_success:
            last = RuntimeError(f"{name}: {response.status_code} {response.text[:240]}")
            logger.warning("Gemini %s reddetti: %s", name, response.status_code)
            if response.status_code in {401, 403}:
                raise last
            continue
        data = response.json()
        chunks: list[str] = []
        for candidate in data.get("candidates") or []:
            parts = ((candidate.get("content") or {}).get("parts")) or []
            chunks.extend(str(part.get("text") or "") for part in parts)
        text = "\n".join(chunk for chunk in chunks if chunk).strip()
        if not text:
            last = RuntimeError(f"{name}: boş yanıt")
            continue
        logger.info("Gemini yedek yanıtı: %s (%s karakter)", name, len(text))
        return _as_chat_response(text, name)
    raise last or RuntimeError("Gemini (gemini-3.6-flash) yanıt vermedi.")


def _gemini_client(timeout=None) -> tuple[OpenAI, str] | None:
    key = (settings.gemini_api_key or "").strip()
    if not key:
        return None
    return (
        _openai_client(
            api_key=key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            timeout=timeout or ANALYZE_HTTP_TIMEOUT,
        ),
        _gemini_model_id(),
    )


def _groq_fast_client() -> tuple[OpenAI, str] | None:
    key = (settings.groq_api_key or "").strip()
    if not key:
        return None
    model = (settings.groq_model or "").strip() or "llama-3.1-8b-instant"
    if "gpt-oss-120b" in model:
        model = model.replace("gpt-oss-120b", "gpt-oss-20b")
    return (
        _openai_client(
            api_key=key,
            base_url=settings.groq_base_url,
            timeout=ANALYZE_HTTP_TIMEOUT,
        ),
        model,
    )


def _cerebras_client(timeout=None) -> tuple[OpenAI, str] | None:
    key = (settings.cerebras_api_key or "").strip()
    if not key:
        return None
    model = (settings.cerebras_model or "").strip() or "gemma-4-31b"
    return (
        _openai_client(
            api_key=key,
            base_url=settings.cerebras_base_url or "https://api.cerebras.ai/v1",
            timeout=timeout or ANALYZE_HTTP_TIMEOUT,
        ),
        model,
    )


def _openrouter_analyze_client() -> tuple[OpenAI, str] | None:
    key = (settings.openrouter_api_key or "").strip()
    if not key or _skip_openrouter:
        return None
    return (
        _openai_client(
            api_key=key,
            base_url=settings.openrouter_base_url,
            timeout=ANALYZE_HTTP_TIMEOUT,
            default_headers={
                "HTTP-Referer": "https://tilko.site",
                "X-Title": _ascii_header("TILKO"),
            },
        ),
        _openrouter_fast_model(),
    )


def _provider_chain() -> list[str]:
    primary = (settings.llm_provider or "groq").strip().lower()
    rest = ["groq", "cerebras", "openrouter", "gemini"]
    ordered = [primary] + [name for name in rest if name != primary]
    return ordered


def _named_client(name: str) -> tuple[OpenAI, str] | None:
    if name == "groq":
        return _groq_fast_client()
    if name == "cerebras":
        return _cerebras_client()
    if name == "openrouter":
        return _openrouter_analyze_client()
    if name == "gemini":
        return None if _skip_gemini else _gemini_client()
    if name == "huggingface":
        if not (settings.hf_api_key or "").strip():
            return None
        return (
            _openai_client(api_key=settings.hf_api_key, base_url=settings.hf_base_url),
            settings.hf_model,
        )
    if name == "openai":
        if not (settings.openai_api_key or "").strip():
            return None
        return _openai_client(api_key=settings.openai_api_key), "gpt-4o-mini"
    return None


def _openrouter_fast_model() -> str:
    return ANALYZE_FAST_MODEL


def _openrouter_models_to_try(preferred: str) -> list[str]:
    ordered: list[str] = []
    if preferred:
        ordered.append(preferred)
    for name in OPENROUTER_FREE_MODELS:
        if name not in ordered:
            ordered.append(name)
    return ordered


def _is_openrouter_client(client: OpenAI) -> bool:
    base = str(getattr(client, "base_url", "") or "")
    return "openrouter.ai" in base


def _is_cerebras_client(client: OpenAI) -> bool:
    base = str(getattr(client, "base_url", "") or "")
    return "cerebras.ai" in base


def _rotate_openrouter(exc: Exception) -> bool:
    raw = str(exc).lower()
    return (
        "unavailable for free" in raw
        or "no endpoints found" in raw
        or "model_not_found" in raw
        or "temporarily rate-limited" in raw
        or "error code: 404" in raw
        or "error code: 429" in raw
    )


def _activate_credit_fallback() -> bool:
    """Kota bitince sıradaki ücretsiz sağlayıcıya geç (Groq → Cerebras)."""
    global _skip_openrouter, _openrouter_free_only, _skip_gemini, _chain_index, _active_name
    with _provider_lock:
        _openrouter_free_only = True
        chain = _provider_chain()
        _chain_index += 1
        while _chain_index < len(chain):
            name = chain[_chain_index]
            if name == "openrouter":
                _skip_openrouter = False
            if name == "gemini" and _skip_gemini:
                _chain_index += 1
                continue
            pair = _named_client(name)
            if pair:
                if name != "openrouter":
                    _skip_openrouter = True
                _active_name = name
                logger.warning("Yedek sağlayıcı: %s / %s", name, pair[1])
                return True
            _chain_index += 1
        _skip_gemini = True
        return False


def _fast_analyze_client() -> tuple[OpenAI, str] | None:
    """Analiz: LLM_PROVIDER, olmazsa Groq / Cerebras. OpenRouter anahtarı yolu ele geçirmez."""
    global _active_name
    chain = _provider_chain()
    start = max(0, min(_chain_index, len(chain) - 1))
    for name in chain[start:]:
        pair = _named_client(name)
        if pair:
            _active_name = name
            return pair
    if settings.openai_api_key:
        _active_name = "openai"
        return (
            _openai_client(
                api_key=settings.openai_api_key,
                timeout=ANALYZE_HTTP_TIMEOUT,
            ),
            "gpt-4o-mini",
        )
    return None


@log_openrouter_usage
def _openai_create(messages: list[dict], temperature: float, json_mode: bool):
    acquire_llm_slot()
    try:
        return _openai_create_inner(messages, temperature, json_mode)
    finally:
        release_llm_slot()


def _openai_create_inner(messages: list[dict], temperature: float, json_mode: bool):
    task = usage_task.get() or ""
    fast = task in ANALYZE_TASKS
    pair = _fast_analyze_client() if fast else None
    if pair:
        client, model = pair
        extra = {}
    else:
        client, model = _client()
        if (
            settings.llm_provider == "openrouter"
            and "gpt-oss-120b" in (model or "")
            and fast
        ):
            model = model.replace("gpt-oss-120b", "gpt-oss-20b")
        extra = _reasoning_extra() if not fast else {}
    kwargs: dict = {
        "model": model,
        "temperature": temperature,
        "messages": messages,
        "timeout": ANALYZE_HTTP_TIMEOUT if fast else LLM_HTTP_TIMEOUT,
    }
    if fast:
        kwargs["max_tokens"] = 7000
    if json_mode and not str(model or "").endswith(":free"):
        if not _is_cerebras_client(client):
            kwargs["response_format"] = {"type": "json_object"}
    if extra:
        kwargs["extra_body"] = extra
    if _is_gemini_client(client) or str(model or "").startswith("gemini-"):
        return _gemini_native_completion(messages, temperature, json_mode)
    try:
        return client.chat.completions.create(**kwargs)
    except Exception as exc:
        text = str(exc).lower()
        if kwargs.get("extra_body") and "reasoning" in text:
            kwargs.pop("extra_body", None)
            logger.warning("Reasoning parametresi reddedildi, sade çağrı.")
            return client.chat.completions.create(**kwargs)
        if _is_openrouter_client(client) and _rotate_openrouter(exc):
            last = exc
            for candidate in _openrouter_models_to_try(str(kwargs.get("model") or ""))[1:]:
                kwargs["model"] = candidate
                logger.warning("OpenRouter ücretsiz model kaydırıldı: %s", candidate)
                try:
                    return client.chat.completions.create(**kwargs)
                except Exception as retry_exc:
                    last = retry_exc
                    if not _rotate_openrouter(retry_exc):
                        raise
            raise last
        if _active_name == "groq" and (
            "model_not_found" in text or "error code: 404" in text
        ):
            last = exc
            for candidate in (
                "llama-3.1-8b-instant",
                "llama-3.3-70b-versatile",
                "openai/gpt-oss-20b",
            ):
                if candidate == kwargs.get("model"):
                    continue
                kwargs["model"] = candidate
                logger.warning("Groq model kaydırıldı: %s", candidate)
                try:
                    return client.chat.completions.create(**kwargs)
                except Exception as retry_exc:
                    last = retry_exc
            raise last
        raise


def _chat_openai_compatible(
    system_prompt: str,
    user_prompt: str,
    temperature: float,
) -> dict:
    """OpenAI, Gemini ve Hugging Face router'ı aynı arayüzü konuşur."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    free = str(_openrouter_fast_model() if _active_name == "openrouter" else "").endswith(
        ":free"
    )
    use_json = (not free) and _active_name not in {"cerebras"}
    try:
        response = _openai_create(messages, temperature, json_mode=use_json)
    except Exception as exc:
        if _is_timeout(exc):
            raise RuntimeError(
                "Model yanıtı gecikti. Analizi tekrar dene; uzun videoda ilk kısım işlenir."
            ) from exc
        err = str(exc)
        fallback = "response_format" in err or "json_validate_failed" in err.lower()
        if not fallback:
            raise
        logger.info("JSON modu tutmadı, düz metinle deneniyor.")
        response = _openai_create(messages, temperature, json_mode=False)
        use_json = False
    parsed = _extract_json(_message_text(response.choices[0].message) or "{}")
    notes = _coerce_notes(parsed)
    if use_json and not notes:
        logger.warning("JSON modu boş şablon döndü, düz metinle tekrar.")
        response = _openai_create(messages, temperature, json_mode=False)
        parsed = _extract_json(_message_text(response.choices[0].message) or "{}")
    return parsed


def _throttle_groq() -> None:
    """Ücretsiz katmanda 8K TPM var; çağrılar arasında yer açılmazsa 429 yağar."""
    if _active_name != "groq" and settings.llm_provider != "groq":
        return
    global _groq_next_ok
    with _groq_gate:
        now = time.time()
        wait = _groq_next_ok - now
        if wait > 0:
            logger.info("Groq TPM aralığı: %.1f sn bekleniyor.", wait)
            time.sleep(wait)
        # 8K TPM, ~5-6K jeton/istek → dakikada bir istek güvenli.
        _groq_next_ok = time.time() + 45


def _chat(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.4,
    task: str = "genel",
) -> dict:
    """Kota/geçici hatalarda artan bekleme ile yeniden dener."""
    global _skip_gemini, _chain_index
    last_error: Exception | None = None
    attempt = 0
    task_token = usage_task.set(task or "genel")
    try:
        while attempt < CHAT_RETRIES:
            try:
                _throttle_groq()
                if settings.is_local:
                    answer = _chat_ollama(system_prompt, user_prompt, temperature)
                else:
                    answer = _chat_openai_compatible(system_prompt, user_prompt, temperature)
                capture.record(task, system_prompt, user_prompt, answer)
                return answer
            except ServiceBusyError:
                raise
            except FatalLLMError:
                raise
            except Exception as exc:
                fatal = _fatal_message(str(exc))
                if fatal:
                    if _is_gemini_quota_error(str(exc)):
                        _skip_gemini = True
                    if _activate_credit_fallback():
                        continue
                    raise QuotaExhaustedError(fatal) from exc
                last_error = exc
                if isinstance(exc, UnicodeEncodeError):
                    logger.warning("LLM başlık/karakter kodlaması: %s", exc)
                    raise ConfigurationError(
                        "LLM isteği ASCII olmayan bir HTTP başlığı yüzünden düştü."
                    ) from exc
                if _is_timeout(exc):
                    raise
                if "model_not_found" in str(exc).lower():
                    raise ConfigurationError(
                        f"'{settings.active_model}' bu sağlayıcıda yok. "
                        "Groq: openai/gpt-oss-120b veya openai/gpt-oss-20b. "
                        "OpenRouter: openrouter.ai/models listesinden bir id yaz "
                        "(ücretsiz için sonuna :free ekle)."
                    ) from exc
                if _oversized_request(str(exc)):
                    raise

                wait = _retry_after(str(exc))
                if wait is not None:
                    if wait >= RATE_LIMIT_MAX_WAIT:
                        raise QuotaExhaustedError(
                            "Model şu an meşgul. Bir dakika sonra tekrar dene."
                        ) from exc
                    logger.info("Hız sınırı: %.1f sn bekleniyor.", wait)
                    time.sleep(wait + 1)
                    continue

                attempt += 1
                if attempt < CHAT_RETRIES:
                    logger.warning("LLM çağrısı başarısız (deneme %s): %s", attempt, exc)
                    time.sleep(RETRY_BACKOFF_SECONDS[attempt - 1])
        raise last_error if last_error else RuntimeError("LLM çağrısı başarısız")
    finally:
        usage_task.reset(task_token)


def _run_parallel(jobs: list) -> list[dict]:
    """Her iş, argümansız çağrılabilir bir fonksiyon. Tek bir parça patlarsa akış sürer."""
    if not jobs:
        return []

    fatal_error: list[FatalLLMError] = []
    failures: list[str] = []

    def safe(job):
        if fatal_error:
            return {}
        try:
            return job()
        except FatalLLMError as exc:
            fatal_error.append(exc)
            failures.append(str(exc))
            return {}
        except Exception as exc:
            failures.append(str(exc) or type(exc).__name__)
            logger.error("Parça tamamen başarısız: %s", exc)
            return {}

    with ThreadPoolExecutor(max_workers=min(settings.max_parallel_calls, len(jobs))) as pool:
        results = list(pool.map(safe, jobs))

    if fatal_error:
        raise fatal_error[0]
    if results and failures and all(not item for item in results):
        raise RuntimeError(failures[0])
    return results


def generate_notes(
    chunks: list[str],
    subject: str | None,
    exam_target: str | None = None,
) -> tuple[list[dict], dict]:
    from app.services.exams import prompt_block

    system = NOTES_SYSTEM_PROMPT + "\n\n" + prompt_block(exam_target)
    total = len(chunks)
    jobs = [
        (lambda block=block, i=i: _chat(
            system,
            build_notes_prompt(block, subject, i, total, exam_target),
            task="notes",
        ))
        for i, block in enumerate(chunks, start=1)
    ]
    logger.info("Not üretimi: %s parça", total)
    results = _run_parallel(jobs)
    notes: list[dict] = []
    empty = 0
    for result in results:
        chunk_notes = _coerce_notes(result if isinstance(result, dict) else {})
        if not chunk_notes:
            empty += 1
        notes.extend(chunk_notes)
    if not notes:
        raise RuntimeError(
            f"Altyazı işlenemedi (0/{len(results)} parça başarılı). "
            "Sağlayıcı yanıt vermedi; birkaç dakika bekleyip tekrar dene."
        )
    if empty:
        logger.warning(
            "Not üretiminde %s/%s parça boş kaldı; eldeki notlarla devam.",
            empty,
            len(results),
        )
    notes.sort(key=lambda n: int(float(n.get("timestamp") or 0)))
    persona = merge_personas(
        [result.get("teacher_persona") for result in results if isinstance(result, dict)]
    )
    return notes, persona.model_dump()


def _notes_block(notes: list[dict]) -> str:
    rows = []
    for note in notes:
        points = " | ".join(str(p) for p in (note.get("key_points") or []))
        rows.append(
            f"[{int(float(note.get('timestamp') or 0))}] "
            f"{note.get('title', '')} — {note.get('detail', '')}"
            + (f" || Anahtar: {points}" if points else "")
        )
    return "\n".join(rows)


def _split_evenly(items: list, groups: int) -> list[list]:
    if groups <= 1 or not items:
        return [items]
    size = ceil(len(items) / groups)
    return [items[i : i + size] for i in range(0, len(items), size)]


def _distribute(total: int, buckets: int) -> list[int]:
    base, remainder = divmod(total, buckets)
    return [base + (1 if i < remainder else 0) for i in range(buckets)]


def _fingerprint(text: str) -> str:
    """Aynı soruyu farklı yazımlarla yakalamak için sadeleştirilmiş imza."""
    folded = unicodedata.normalize("NFKD", text.lower())
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return NON_WORD_RE.sub(" ", folded).strip()[:90]


def _is_valid(question: dict) -> bool:
    text = str(question.get("text") or "").strip()
    options = question.get("options") or {}
    correct = str(question.get("correct") or "").strip().upper()[:1]
    if len(text) < 15 or not isinstance(options, dict):
        return False
    keys = {str(k).strip().upper() for k in options}
    if not set(OPTION_KEYS).issubset(keys):
        return False
    if any(not str(v).strip() for v in options.values()):
        return False
    return correct in OPTION_KEYS


def _collect(
    results: list[dict],
    questions: list[dict],
    seen: set[str],
    limit: int,
) -> None:
    for result in results:
        for item in _dicts(result.get("questions") if isinstance(result, dict) else None):
            if len(questions) >= limit:
                return
            if not _is_valid(item):
                continue
            key = _fingerprint(str(item.get("text")))
            if key in seen:
                continue
            seen.add(key)
            questions.append(item)


def generate_questions(
    notes: list[dict],
    subject: str | None,
    question_count: int,
    persona: dict | None = None,
    exam_target: str | None = None,
    subject_type: str | None = None,
    is_yks_fen_question: bool = False,
    rag_block: str = "",
) -> list[dict]:
    if not notes or question_count <= 0:
        return []

    from app.services.exams import prompt_block
    from app.services.subjects import classify, parse_premises, parse_steps

    meta = classify(
        subject=subject,
        subject_type=subject_type,
        exam_target=exam_target,
        is_yks_fen_question=is_yks_fen_question,
    )
    kind = meta["subject_type"]
    fen = bool(meta["is_yks_fen_question"])

    system = (
        questions_system_for(subject_type=kind, is_yks_fen_question=fen)
        + "\n\n"
        + prompt_block(exam_target)
        + "\n\n"
        + (rag_block or "")
        + "\n\n"
        + persona_system_block(persona)
    )
    groups = _split_evenly(notes, max(1, ceil(question_count / settings.questions_per_call)))
    counts = _distribute(question_count, len(groups))

    questions: list[dict] = []
    seen: set[str] = set()

    jobs = [
        (lambda group=group, count=count: _chat(
            system,
            build_questions_prompt(
                _notes_block(group),
                subject,
                count,
                exam_target=exam_target,
                subject_type=kind,
                is_yks_fen_question=fen,
                rag_block=rag_block,
            ),
            task="questions",
        ))
        for group, count in zip(groups, counts)
        if count > 0
    ]
    _collect(_run_parallel(jobs), questions, seen, question_count)

    # Eksik kalırsa (kota hatası, tekrar ayıklama veya model az üretti) tamamla.
    for round_index in range(TOPUP_ROUNDS):
        missing = question_count - len(questions)
        if missing <= 0:
            break
        logger.info("Soru tamamlama turu %s: %s soru eksik", round_index + 1, missing)
        avoid = [str(q.get("text")) for q in questions]
        topup_groups = _split_evenly(
            notes, max(1, ceil(missing / settings.questions_per_call))
        )
        topup_counts = _distribute(missing, len(topup_groups))
        topup_jobs = [
            (lambda group=group, count=count: _chat(
                system,
                build_questions_prompt(
                    _notes_block(group),
                    subject,
                    count,
                    avoid,
                    exam_target,
                    kind,
                    fen,
                    rag_block,
                ),
                temperature=0.7,
                task="questions",
            ))
            for group, count in zip(topup_groups, topup_counts)
            if count > 0
        ]
        before = len(questions)
        _collect(_run_parallel(topup_jobs), questions, seen, question_count)
        if len(questions) == before:
            logger.warning("Tamamlama turu yeni soru getirmedi, durduruluyor.")
            break

    questions.sort(
        key=lambda q: (
            DIFFICULTY_ORDER.get(str(q.get("difficulty") or "").strip().lower(), 1),
            int(float(q.get("timestamp") or 0)),
        )
    )
    trimmed = questions[:question_count]
    for item in trimmed:
        item["subject_type"] = kind
        item["is_yks_fen_question"] = fen
        item["fen_branch"] = meta["fen_branch"] or str(item.get("fen_branch") or "")
        item["misconception_tag"] = meta["misconception_tag"] or str(
            item.get("misconception_tag") or ""
        )
        item["step_by_step_solution"] = parse_steps(item.get("step_by_step_solution"))
        item["shortcut_tactic"] = str(item.get("shortcut_tactic") or "").strip()
        item["premises"] = parse_premises(item.get("premises"))
    return trimmed


def _rechunk(chunks: list[str], max_chars: int) -> list[str]:
    """Yedeğe geçince (ör. Groq 8K → Ollama 4K) parçaları yeniden kes."""
    out: list[str] = []
    for block in chunks:
        if len(block) <= max_chars:
            out.append(block)
            continue
        buf: list[str] = []
        size = 0
        for line in block.splitlines():
            extra = len(line) + 1
            if buf and size + extra > max_chars:
                out.append("\n".join(buf))
                buf = [line]
                size = extra
            else:
                buf.append(line)
                size += extra
        if buf:
            out.append("\n".join(buf))
    return out or chunks


def complete_json(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.4,
    task: str = "genel",
) -> dict:
    """JSON nesnesi bekleyen kısa LLM çağrıları (teşhis, check-up)."""
    return _chat(system_prompt, user_prompt, temperature=temperature, task=task)


def analyze_transcript(
    chunks: list[str],
    subject: str | None,
    question_count: int,
    exam_target: str | None = None,
    subject_type: str | None = None,
    is_yks_fen_question: bool = False,
    rag_block: str = "",
) -> dict:
    try:
        return _analyze_once(
            chunks,
            subject,
            question_count,
            exam_target,
            subject_type,
            is_yks_fen_question,
            rag_block,
        )
    except QuotaExhaustedError as exc:
        fallback = (settings.llm_fallback or "").strip().lower()
        if not fallback or fallback == settings.llm_provider:
            raise
        logger.warning(
            "%s kotası bitti, yedek sağlayıcıya geçiliyor (%s): %s",
            settings.llm_provider,
            fallback,
            exc,
        )
        with _provider_lock:
            previous = settings.llm_provider
            settings.llm_provider = fallback
            try:
                work = chunks
                if work and settings.chunk_chars < max(len(c) for c in work):
                    work = _rechunk(work, settings.chunk_chars)
                return _analyze_once(
                    work,
                    subject,
                    question_count,
                    exam_target,
                    subject_type,
                    is_yks_fen_question,
                    rag_block,
                )
            finally:
                settings.llm_provider = previous


def _analyze_combined(
    chunk: str,
    subject: str | None,
    question_count: int,
    exam_target: str | None,
    subject_type: str | None,
    is_yks_fen_question: bool,
    rag_block: str,
    window_label: str = "",
    note_count: int = 5,
) -> dict:
    from app.services.exams import prompt_block

    count = max(2, min(int(question_count or 4), 6))
    system = (
        "Kısa Türkçe sınav notu ve 5 şıklı soru yaz. Sadece JSON. "
        "Markdown, kod çiti ve uzun düşünme yok.\n\n"
        + prompt_block(exam_target)
        + questions_system_for(
            subject_type=subject_type,
            is_yks_fen_question=is_yks_fen_question,
        )
    )
    logger.info("Dilim analiz: %s not/%s soru %s", note_count, count, window_label or "")
    result = _as_dict(
        _chat(
            system,
            build_combined_analyze_prompt(
                chunk,
                subject,
                count,
                exam_target,
                rag_block,
                window_label,
                note_count,
            ),
            task="analyze",
        )
    )
    notes = _coerce_notes(result)
    if not notes:
        logger.warning("Birleşik analiz boş not döndü; kısa not denemesi.")
        result = _as_dict(
            _chat(
                "Kısa Türkçe sınav notu yaz. Sadece JSON. notes boş olamaz.",
                (
                    f"Ders: {subject or 'KPSS'}\nAltyazı:\n{chunk[:4000]}\n\n"
                    "En az 3 not yaz. Şema: "
                    '{"notes":[{"title":"...","detail":"...","key_points":["..."],'
                    '"mnemonic":"...","exam_tip":"...","timestamp":0}]}'
                ),
                task="analyze",
            )
        )
        notes = _coerce_notes(result)
    if not notes:
        raise RuntimeError(
            "Model not yazamadı. Ücretsiz model boş yanıt verdi; bir kez daha dene."
        )
    questions: list[dict] = []
    seen: set[str] = set()
    _collect([result], questions, seen, count)
    persona = merge_personas([result.get("teacher_persona")])
    return {
        "notes": notes,
        "questions": questions,
        "teacher_persona": persona.model_dump(),
    }


def analyze_slice(
    chunk: str,
    subject: str | None,
    question_count: int,
    exam_target: str | None,
    subject_type: str | None,
    is_yks_fen_question: bool,
    rag_block: str = "",
    window_label: str = "",
    note_count: int = 5,
) -> dict:
    """Tek 5 dakikalık dilimi not + soruya çevirir."""
    return _analyze_combined(
        chunk,
        subject,
        question_count,
        exam_target,
        subject_type,
        is_yks_fen_question,
        rag_block,
        window_label,
        note_count,
    )


def _analyze_once(
    chunks: list[str],
    subject: str | None,
    question_count: int,
    exam_target: str | None = None,
    subject_type: str | None = None,
    is_yks_fen_question: bool = False,
    rag_block: str = "",
) -> dict:
    work = list(chunks or [])[: max(1, settings.max_analyze_chunks)]
    count = max(1, min(int(question_count or 8), 8))
    logger.info(
        "Analiz: %s/%s parça, %s soru, model=%s",
        len(work),
        len(chunks or []),
        count,
        settings.active_model,
    )
    if settings.is_reasoning_model and work:
        return _analyze_combined(
            work[0],
            subject,
            count,
            exam_target,
            subject_type,
            is_yks_fen_question,
            rag_block,
        )
    notes, persona = generate_notes(work, subject, exam_target)
    if not notes:
        raise RuntimeError(
            "Model not üretemedi. Videonun altyazısı çok kısa olabilir veya "
            "LLM sağlayıcısı yanıt vermedi."
        )
    logger.info("Notlar hazır (%s), soru üretiliyor", len(notes))
    questions = generate_questions(
        notes,
        subject,
        count,
        persona,
        exam_target,
        subject_type,
        is_yks_fen_question,
        rag_block,
    )
    return {"notes": notes, "questions": questions, "teacher_persona": persona}


def generate_coach_script(
    trap_lines: str,
    title: str | None = None,
    exam_target: str | None = None,
) -> str:
    """Günün tuzak özetini seslendirilecek kısa bir konuşmaya çevirir."""
    rank = title or "Acemi Tilki"
    if not trap_lines.strip():
        return (
            f"Hey {rank}, bugün tuzak defterin boş. Bu iyi haber değil, henüz savaşmadın demek. "
            "Bir video analiz et, yanlışlarını kaydet, yarın seni bekleyeceğim."
        )
    try:
        from app.services.exams import prompt_block

        answer = _chat(
            COACH_SYSTEM_PROMPT + "\n\n" + prompt_block(exam_target),
            build_coach_prompt(trap_lines, rank, exam_target),
            temperature=0.5,
            task="coach",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Koç metni üretilemedi, şablon kullanılacak: %s", exc)
        return (
            f"Hey {rank}, bugün tuzaklara düştün. Çeldiricileri tekrar oku, süre tuzağına düştüysen "
            "saate bakarak çöz. Yarın aynı sorular seni bekliyor."
        )
    script = str(answer.get("script") or "").strip()
    return script or f"Hey {rank}, bugünün tuzaklarını aç, her çeldiriciyi bir cümleyle tekrar et."
