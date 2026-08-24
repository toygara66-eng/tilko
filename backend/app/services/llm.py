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
LLM_HTTP_TIMEOUT = httpx.Timeout(120.0, connect=15.0)
# Analiz: Groq hızlı bitsin; Gemini yedek ve kısa kapı.
ANALYZE_HTTP_TIMEOUT = httpx.Timeout(28.0, connect=8.0)
GEMINI_ANALYZE_TIMEOUT = httpx.Timeout(16.0, connect=8.0)
ANALYZE_TASKS = frozenset({"analyze", "notes", "questions"})
ANALYZE_FAST_MODEL = "nvidia/nemotron-3-nano-30b-a3b:free"
GEMINI_CHAT_MODEL = "gemini-2.5-flash-lite"
# flash-lite ≈ hızlı/ucuz; 2.0-flash yalnızca yedek (analiz zincirinde tek model deneriz).
GEMINI_MODEL_FALLBACKS = (
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
)
GEMINI_UNAVAILABLE_MODELS = frozenset(
    {
        "gemini-2.5-flash",
        "gemini-2.5-pro",
        "gemini-1.5-pro",
        "gemini-1.5-pro-latest",
    }
)
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
_last_chance_used = False
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
            _normalize_groq_model(settings.groq_model),
        )

    if settings.llm_provider == "cerebras":
        pair = _cerebras_client(timeout=LLM_HTTP_TIMEOUT)
        if not pair:
            raise ConfigurationError(
                "CEREBRAS_API_KEY tanımlı değil. cloud.cerebras.ai adresinden "
                "ücretsiz anahtar al (kart istemez, günde ~1M jeton)."
            )
        return pair

    if settings.llm_provider == "nebius":
        pair = _nebius_client(timeout=LLM_HTTP_TIMEOUT)
        if not pair:
            raise ConfigurationError(
                "NEBIUS_API_KEY tanımlı değil. tokenfactory.nebius.com adresinden "
                "anahtar al (yeni hesapta genelde deneme kredisi var)."
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
    if "payment_required" in text or "payment required" in text:
        return "quota" in text or "billing" in text or "gemini" in text
    googleish = (
        "generativelanguage.googleapis.com" in text
        or "gemini" in text
        or "you exceeded your current quota" in text
        or "resource_exhausted" in text
    )
    return googleish and (
        "quota" in text
        or "resource_exhausted" in text
        or "429" in raw
        or "402" in raw
    )


def _is_payment_or_credit_error(raw: str) -> bool:
    text = raw.lower()
    return (
        "payment_required" in text
        or "payment required" in text
        or "error code: 402" in text
        or "billing tab" in text
        or "insufficient credits" in text
        or "insufficient_quota" in text
        or ("requires at least" in text and "credit" in text)
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
    if _is_payment_or_credit_error(raw) or (
        ("credit" in text or "balance" in text)
        and (
            settings.llm_provider == "openrouter"
            or "openrouter" in text
            or _active_name == "openrouter"
        )
    ):
        if _chain_index > 0:
            return (
                "Ücretsiz yedekler de yanıt vermedi. Render'da GROQ_API_KEY ve "
                "CEREBRAS_API_KEY dolu olsun."
            )
        return "Ücretli kota/kredi bitti; Groq/Cerebras yedeğine geçiliyor."
    if "tokens per day" in text or ("per day" in text and settings.llm_provider == "groq"):
        # Rolling TPD: 'try again in 5m' ise beklemek yeterli; saatlerceyse gerçekten bitti.
        wait = _retry_after(raw)
        if wait is None or wait >= RATE_LIMIT_MAX_WAIT:
            return (
                "Groq'un günlük ücretsiz jeton sınırı doldu. "
                "Cerebras yedeği varsa ona geçilir; yoksa yarın tekrar dene."
            )
    if _is_gemini_quota_error(raw) or (
        "exceeded your current quota" in text
        or ("429" in raw and "quota" in text and "gemini" in text)
    ):
        if _groq_fast_client() or _cerebras_client():
            return "Gemini ücretsiz kotası doldu; ücretsiz yedeğe geçiliyor."
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


def _content_tokens(text: str) -> set[str]:
    return {part.lower() for part in re.findall(r"[A-Za-zÇĞİÖŞÜçğıöşü0-9]{5,}", text or "")}


def _fold_tr(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").casefold()).strip()


_PROMO_NOTE_RE = re.compile(
    r"("
    r"ücretsiz\s*pdf|pdf'?i?\s*indir|kolay\s*erişim|"
    r"telegram|whatsapp|instagram|discord|"
    r"abone\s*ol|beğen\s*meyi|kanalıma\s*abone|"
    r"satın\s*al|sipariş\s*ver|kampanya|sponsor|"
    r"korsan\s*kitap|korsan\s*pdf|indirim\s*kod|"
    r"yayınevi|yayinevi|sosyal\s*medya\s*hesab|"
    r"çekiliş|hediye\s*kod|promosyon|"
    r"hakkım\s*(sonuna|helal)|destek\s*ol(arak)?\s*abone"
    r")",
    re.IGNORECASE,
)


def _is_promo_note(note: dict) -> bool:
    blob = " ".join(
        [
            str(note.get("title") or ""),
            str(note.get("detail") or ""),
            str(note.get("mnemonic") or ""),
            str(note.get("exam_tip") or ""),
            " ".join(str(p) for p in (note.get("key_points") or [])),
        ]
    )
    return bool(_PROMO_NOTE_RE.search(blob))


def _normalize_for_match(text: str) -> str:
    folded = _fold_tr(text)
    cleaned = re.sub(r"[^\w\s]", " ", folded, flags=re.UNICODE)
    return re.sub(r"\s+", " ", cleaned).strip()


def _span_in_transcript(span: str, folded_norm: str) -> bool:
    """Birebir veya noktalama farkıyla altyazıda geçiyor mu."""
    needle = _normalize_for_match(span)
    if len(needle) < 8:
        return False
    if needle in folded_norm:
        return True
    words = needle.split()
    if len(words) >= 5:
        for index in range(0, len(words) - 4):
            if " ".join(words[index : index + 5]) in folded_norm:
                return True
    if len(words) >= 3 and " ".join(words[:4]) in folded_norm:
        return True
    return False


def _ground_notes(notes: list[dict], transcript: str) -> list[dict]:
    """Tanıtım notlarını at; altyazıyla bağını gevşek doğrula (sıkı quote modeli öldürmesin)."""
    source = _content_tokens(transcript)
    folded_norm = _normalize_for_match(transcript)
    if not notes:
        return []
    if not source and not folded_norm:
        return []
    kept: list[dict] = []
    for note in notes:
        if _is_promo_note(note):
            continue
        quote = str(
            note.get("quote")
            or note.get("alinti")
            or note.get("alıntı")
            or ""
        ).strip()
        title = str(note.get("title") or "").strip()
        detail = str(note.get("detail") or "").strip()
        if not title and not detail:
            continue
        blob = f"{title} {detail} {' '.join(str(p) for p in (note.get('key_points') or []))}"
        tokens = _content_tokens(blob)
        overlap = tokens & source if source else set()
        quote_ok = bool(quote) and _span_in_transcript(quote, folded_norm)
        detail_ok = len(detail) >= 36 and _span_in_transcript(detail[:100], folded_norm)
        soft_ok = len(overlap) >= 2 and len(detail) >= 24
        if quote_ok or detail_ok or soft_ok:
            kept.append(note)
    if kept:
        return kept
    # Model quote'u bozsa bile ders notunu tamamen düşürme.
    soft = [
        note
        for note in notes
        if not _is_promo_note(note)
        and len(str(note.get("detail") or note.get("title") or "").strip()) >= 24
    ]
    if soft:
        logger.warning(
            "Sıkı grounding 0 not bıraktı; %s not yumuşak kabul edildi.",
            len(soft),
        )
        return soft[:8]
    return []


def _ground_questions(questions: list[dict], transcript: str) -> list[dict]:
    source = _content_tokens(transcript)
    if not questions or not source:
        return questions
    kept: list[dict] = []
    for item in questions:
        options = item.get("options") or {}
        blob = " ".join(
            [
                str(item.get("text") or ""),
                str(item.get("explanation") or ""),
                " ".join(str(v) for v in options.values()),
            ]
        )
        tokens = _content_tokens(blob)
        overlap = tokens & source
        if not tokens or len(overlap) >= 2 or len(overlap) / max(len(tokens), 1) >= 0.12:
            kept.append(item)
    return kept if kept else questions


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
    return (
        "timed out" in text
        or "timeout" in text
        or "time-out" in text
        or "gecikti" in text
        or "zaman aşım" in text
        or "zaman asim" in text
    )


def _reasoning_extra() -> dict:
    """gpt-oss varsayılan düşünme çabasıyla her not turunu dakikalarca uzatır."""
    if not settings.is_reasoning_model:
        return {}
    return {"reasoning": {"effort": "minimal", "exclude": True}}


def _gemini_model_id() -> str:
    raw = (settings.gemini_model or "").strip() or GEMINI_CHAT_MODEL
    # Render'da kalan GEMINI_MODEL=gemini-2.5-flash → 404; sessizce güvenli modele al.
    if raw in GEMINI_UNAVAILABLE_MODELS:
        logger.warning(
            "GEMINI_MODEL=%s bu anahtarlarda sık 404; %s kullanılıyor.",
            raw,
            GEMINI_CHAT_MODEL,
        )
        return GEMINI_CHAT_MODEL
    return raw


def _gemini_models_to_try() -> list[str]:
    """Analizde tek Gemini modeli; timeout olursa Groq'a düş (2× beklemeyi kes)."""
    primary = _gemini_model_id()
    # Render hâlâ 2.0-flash gösterse bile analizde lite'ı tercih et (hız).
    task = usage_task.get() or ""
    if task in ANALYZE_TASKS:
        # Önce lite, yoksa yapılandırılan.
        for name in (GEMINI_CHAT_MODEL, primary):
            if name and name not in GEMINI_UNAVAILABLE_MODELS:
                return [name]
        return [GEMINI_CHAT_MODEL]
    ordered: list[str] = []
    for name in (primary, *GEMINI_MODEL_FALLBACKS):
        if not name or name in GEMINI_UNAVAILABLE_MODELS:
            continue
        if name not in ordered:
            ordered.append(name)
        if len(ordered) >= 2:
            break
    return ordered or [GEMINI_CHAT_MODEL]


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
    # Çok uzun prompt Gemini'yi kilitleyip timeout üretir; detayı koruyarak budar.
    if len(user) > 9000:
        user = user[:9000] + "\n...(altyazı kısaltıldı; yine detaylı not yaz)"
    if len(system) > 3500:
        system = system[:3500] + "\n...(kısaltıldı)"
    last: Exception | None = None
    models = _gemini_models_to_try()
    for index, name in enumerate(models):
        # Analiz: kısa çıktı = daha az timeout.
        task = usage_task.get() or ""
        if task in ANALYZE_TASKS:
            out_tokens = 1600
        else:
            out_tokens = 3200 if index == 0 else 2200
        generation = {
            "temperature": temperature,
            "maxOutputTokens": out_tokens,
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
                timeout=GEMINI_ANALYZE_TIMEOUT,
            )
        except Exception as exc:  # noqa: BLE001
            last = exc
            logger.warning("Gemini %s ağ hatası: %s", name, exc)
            if _is_timeout(exc):
                # Analizde ikinci Gemini modelini deneme — hemen Groq yedeğine çık.
                raise TimeoutError(f"Gemini {name} timed out") from exc
            continue
        if response.status_code == 400 and "thinking" in (response.text or "").lower():
            generation.pop("thinkingConfig", None)
            payload["generationConfig"] = generation
            try:
                response = httpx.post(
                    url,
                    headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                    json=payload,
                    timeout=GEMINI_ANALYZE_TIMEOUT,
                )
            except Exception as exc:  # noqa: BLE001
                last = exc
                if _is_timeout(exc):
                    raise TimeoutError(f"Gemini {name} timed out") from exc
                continue
        if response.status_code == 404:
            logger.warning("Gemini model yok, sıradaki: %s", name)
            last = RuntimeError(f"Gemini model yok: {name}")
            continue
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
        # MAX_TOKENS ile kesilmiş JSON sık gelir — yine de parse etmeyi dene.
        logger.info("Gemini yanıtı: %s (%s karakter)", name, len(text))
        return _as_chat_response(text, name)
    if last and _is_timeout(last):
        raise TimeoutError(str(last) or "Gemini timed out") from last
    raise last or RuntimeError("Gemini yanıt vermedi.")


def _normalize_groq_model(raw: str | None) -> str:
    """Analizde yalnızca hızlı/ucuz Llama; gpt-oss 8K TPM ile patlıyor."""
    model = (raw or "").strip() or "llama-3.1-8b-instant"
    lowered = model.lower()
    if (
        "gpt-oss" in lowered
        or "120b" in lowered
        or "70b" in lowered
        or lowered in {"", "auto", "default"}
    ):
        return "llama-3.1-8b-instant"
    return model


def _shrink_prompts_for_provider(
    system_prompt: str, user_prompt: str
) -> tuple[str, str]:
    """Groq 8K TPM + genel analiz hızı: girdi tavanı."""
    name = (_active_name or settings.llm_provider or "").strip().lower()
    task = usage_task.get() or ""
    system = system_prompt
    user = user_prompt
    # Analizde her sağlayıcıda kısa tut — timeout'un ana nedeni uzun prompt.
    if task in ANALYZE_TASKS:
        sys_cap, user_cap = (1800, 3200) if name == "groq" else (2400, 4200)
        if len(system) > sys_cap:
            system = system[:sys_cap] + "\n...(kısaltıldı)"
        if len(user) > user_cap:
            head = user[:700]
            tail = user[-500:] if len(user) > 1200 else ""
            mid_budget = user_cap - len(head) - len(tail) - 40
            mid = user[700 : 700 + max(400, mid_budget)]
            user = f"{head}\n{mid}\n...(altyazı kısaltıldı)\n{tail}".strip()
        return system, user
    if name != "groq":
        return system_prompt, user_prompt
    if len(system) > 2500:
        system = system[:2500] + "\n...(kısaltıldı)"
    if len(user) > 4200:
        head = user[:800]
        tail = user[-600:] if len(user) > 1400 else ""
        mid_budget = 4200 - len(head) - len(tail) - 40
        mid = user[800 : 800 + max(500, mid_budget)]
        user = f"{head}\n{mid}\n...(altyazı kısaltıldı)\n{tail}".strip()
    return system, user


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
    return (
        _openai_client(
            api_key=key,
            base_url=settings.groq_base_url,
            timeout=ANALYZE_HTTP_TIMEOUT,
        ),
        _normalize_groq_model(settings.groq_model),
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


def _nebius_client(timeout=None) -> tuple[OpenAI, str] | None:
    key = (settings.nebius_api_key or "").strip()
    if not key:
        return None
    model = (settings.nebius_model or "").strip() or "Qwen/Qwen3-32B"
    base = (settings.nebius_base_url or "").strip() or "https://api.tokenfactory.nebius.com/v1/"
    if not base.endswith("/"):
        base += "/"
    return (
        _openai_client(
            api_key=key,
            base_url=base,
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


def _named_client(name: str) -> tuple[OpenAI, str] | None:
    if name == "nebius":
        return _nebius_client()
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


def analyze_llm_ready() -> dict[str, bool | str]:
    """Render env: Gemini / Nebius / Cerebras / Groq."""
    gemini = bool((settings.gemini_api_key or "").strip())
    nebius = bool((settings.nebius_api_key or "").strip())
    groq = bool((settings.groq_api_key or "").strip())
    cerebras = bool((settings.cerebras_api_key or "").strip())
    provider = (settings.llm_provider or "").strip().lower()
    model = str(settings.active_model or "")
    if provider == "gemini" and gemini:
        raw = (settings.gemini_model or "").strip()
        if raw in GEMINI_UNAVAILABLE_MODELS:
            model = GEMINI_CHAT_MODEL
        else:
            model = raw or GEMINI_CHAT_MODEL
    elif provider == "nebius" and nebius:
        model = (settings.nebius_model or "").strip() or model
    elif provider == "cerebras" and cerebras:
        model = (settings.cerebras_model or "").strip() or model
    elif provider == "groq" and groq:
        model = _normalize_groq_model(settings.groq_model)
    ready = False
    if provider == "gemini":
        ready = gemini
    elif provider == "nebius":
        ready = nebius
    elif provider == "cerebras":
        ready = cerebras
    elif provider == "groq":
        ready = groq
    else:
        ready = gemini or nebius or groq or cerebras
    return {
        "gemini": gemini,
        "nebius": nebius,
        "groq": groq,
        "cerebras": cerebras,
        "ready": ready,
        "provider": provider or settings.llm_provider,
        "model": model,
    }


def require_analyze_llm() -> None:
    status = analyze_llm_ready()
    if status["ready"]:
        return
    raise ConfigurationError(
        "Analiz için GEMINI_API_KEY (önerilen) veya NEBIUS_API_KEY / "
        "CEREBRAS_API_KEY / GROQ_API_KEY gerekli. "
        "Render Environment'a yazıp LLM_PROVIDER=gemini yap."
    )


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


def _is_nebius_client(client: OpenAI) -> bool:
    base = str(getattr(client, "base_url", "") or "")
    return "nebius.com" in base or "nebius.ai" in base


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


def _provider_chain() -> list[str]:
    """Analiz: önce hızlı yedekler (Groq/Cerebras), Gemini kalite için sonra."""
    preferred = (settings.llm_provider or "gemini").strip().lower()
    # Hız öncelikli sıra — "yavaş kaldı"yı kesmek için.
    speed_first = ["groq", "cerebras", "gemini", "nebius"]
    if preferred == "openrouter":
        return ["openrouter", *speed_first]
    if preferred == "ollama":
        return ["ollama"]
    # Gemini seçili olsa bile analizde Groq önce (timeout / kota dayanıklılığı).
    if preferred in {"gemini", "groq", "cerebras", "nebius"}:
        return list(speed_first)
    return list(speed_first)


def reset_analyze_provider_chain() -> None:
    """Her video işi temiz sırayla başlasın (önceki timeout zinciri kalmasın)."""
    global _chain_index, _active_name, _last_chance_used, _skip_gemini
    with _provider_lock:
        _chain_index = 0
        _active_name = ""
        _last_chance_used = False
        _skip_gemini = False


def _activate_next_analyze_provider(*, reason: str = "yedek") -> bool:
    """Timeout / geçici hatada sıradaki analiz sağlayıcısına geç."""
    global _chain_index, _active_name
    with _provider_lock:
        chain = _provider_chain()
        _chain_index += 1
        while _chain_index < len(chain):
            name = chain[_chain_index]
            pair = _named_client(name)
            if pair:
                _active_name = name
                logger.warning(
                    "Analiz sağlayıcı kaydırıldı (%s): %s / %s",
                    reason,
                    name,
                    pair[1],
                )
                return True
            _chain_index += 1
        return False


def _force_fast_fallback_provider() -> bool:
    """Zincir bittiğinde son şans: Groq/Cerebras/Nebius'tan ilkini zorla (bir kez)."""
    global _chain_index, _active_name, _skip_gemini, _last_chance_used
    with _provider_lock:
        if _last_chance_used:
            return False
        _skip_gemini = True
        for name in ("groq", "cerebras", "nebius"):
            pair = _named_client(name)
            if not pair:
                continue
            chain = _provider_chain()
            try:
                _chain_index = chain.index(name)
            except ValueError:
                _chain_index = max(_chain_index, 0)
            _active_name = name
            _last_chance_used = True
            logger.warning("Son şans yedek: %s / %s", name, pair[1])
            return True
        return False


def _activate_credit_fallback() -> bool:
    """Kota bitince sıradaki sağlayıcıya geç (Gemini kota → Groq/Cerebras/Nebius)."""
    global _skip_openrouter, _openrouter_free_only, _skip_gemini, _chain_index, _active_name
    with _provider_lock:
        _openrouter_free_only = True
        _skip_openrouter = True
        _skip_gemini = True
        chain = _provider_chain()
        # Mevcut (bitmiş) sağlayıcıyı atla.
        _chain_index = max(_chain_index + 1, 0)
        while _chain_index < len(chain):
            name = chain[_chain_index]
            if name in {"openrouter", "gemini"}:
                _chain_index += 1
                continue
            pair = _named_client(name)
            if pair:
                _active_name = name
                logger.warning("Yedek sağlayıcı: %s / %s", name, pair[1])
                return True
            _chain_index += 1
        return False


def _fast_analyze_client() -> tuple[OpenAI, str] | None:
    """Analiz: Gemini → Groq → Cerebras → Nebius (yapılandırılmış sırayla)."""
    global _active_name
    require_analyze_llm()
    chain = _provider_chain()
    start = max(0, min(_chain_index, len(chain) - 1))
    for name in chain[start:]:
        pair = _named_client(name)
        if pair:
            _active_name = name
            return pair
    raise ConfigurationError(
        "GEMINI_API_KEY / GROQ_API_KEY / CEREBRAS_API_KEY / NEBIUS_API_KEY "
        "tanımlı değil. Render Environment'a en az birini yaz."
    )


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
        # Groq free TPM ~8K; düşük max_tokens hem 413 hem süreyi keser.
        if (_active_name or settings.llm_provider or "").lower() == "groq":
            kwargs["max_tokens"] = 900
        else:
            kwargs["max_tokens"] = 1800
    model_id = str(model or "")
    if (
        json_mode
        and not model_id.endswith(":free")
        and "8b" not in model_id
        and not _is_cerebras_client(client)
    ):
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
            "model_not_found" in text
            or "error code: 404" in text
            or _oversized_request(text)
        ):
            last = exc
            for candidate in (
                "llama-3.1-8b-instant",
                "llama-3.3-70b-versatile",
            ):
                if candidate == kwargs.get("model"):
                    continue
                kwargs["model"] = candidate
                if "8b" in candidate:
                    kwargs.pop("response_format", None)
                if _oversized_request(text):
                    kwargs["max_tokens"] = min(int(kwargs.get("max_tokens") or 1200), 1000)
                    # Mesajları da kısalt.
                    msgs = list(kwargs.get("messages") or [])
                    trimmed = []
                    for message in msgs:
                        row = dict(message)
                        content = str(row.get("content") or "")
                        if row.get("role") == "user" and len(content) > 3500:
                            row["content"] = content[:3500] + "\n...(kısaltıldı)"
                        elif row.get("role") == "system" and len(content) > 2000:
                            row["content"] = content[:2000] + "\n...(kısaltıldı)"
                        trimmed.append(row)
                    kwargs["messages"] = trimmed
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
    task = usage_task.get() or ""
    if task in ANALYZE_TASKS:
        try:
            _fast_analyze_client()  # _active_name + shrink doğru olsun
        except Exception:
            pass
    system_prompt, user_prompt = _shrink_prompts_for_provider(
        system_prompt, user_prompt
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    free = str(_openrouter_fast_model() if _active_name == "openrouter" else "").endswith(
        ":free"
    )
    active = (_active_name or settings.llm_provider or "").strip().lower()
    # Groq/Cerebras: json_object + ikinci çağrı timeout üretir.
    use_json = (not free) and active not in {"cerebras", "groq"}
    try:
        response = _openai_create(messages, temperature, json_mode=use_json)
    except Exception as exc:
        # Timeout'u burada yutma: _chat yedek sağlayıcıya geçebilsin.
        if _is_timeout(exc):
            raise
        if _oversized_request(str(exc)):
            # Bir kez daha agresif kısaltıp dene.
            system_prompt, user_prompt = _shrink_prompts_for_provider(
                system_prompt[:1400], user_prompt[:2400]
            )
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt + "\n\nDaha kısa JSON yaz."},
            ]
            logger.warning("İstek fazla büyüdü; kısaltılmış tekrar.")
            response = _openai_create(messages, temperature, json_mode=False)
            use_json = False
        else:
            err = str(exc)
            fallback = "response_format" in err or "json_validate_failed" in err.lower()
            if not fallback:
                raise
            logger.info("JSON modu tutmadı, düz metinle deneniyor.")
            response = _openai_create(messages, temperature, json_mode=False)
            use_json = False
    parsed = _extract_json(_message_text(response.choices[0].message) or "{}")
    # İkinci LLM çağrısı YASAK (timeout katlar); boşsa üst katman yumuşak not alır.
    return parsed


def _throttle_groq() -> None:
    """Ücretsiz katmanda TPM var; analiz failover'da 45 sn bekletme."""
    if _active_name != "groq" and settings.llm_provider != "groq":
        return
    global _groq_next_ok
    task = usage_task.get() or ""
    gap = 4.0 if task in ANALYZE_TASKS else 45.0
    with _groq_gate:
        now = time.time()
        wait = _groq_next_ok - now
        if wait > 0:
            logger.info("Groq TPM aralığı: %.1f sn bekleniyor.", wait)
            time.sleep(wait)
        _groq_next_ok = time.time() + gap


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
        while attempt < CHAT_RETRIES + 4:
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
                    if _is_gemini_quota_error(str(exc)) or _is_payment_or_credit_error(str(exc)):
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
                    if task in ANALYZE_TASKS and _activate_next_analyze_provider(
                        reason="timeout"
                    ):
                        # Groq için promptu küçült (8K TPM).
                        system_prompt, user_prompt = _shrink_prompts_for_provider(
                            system_prompt, user_prompt
                        )
                        logger.warning(
                            "Timeout → yedek sağlayıcı: %s", _active_name or "?"
                        )
                        continue
                    if task in ANALYZE_TASKS and _force_fast_fallback_provider():
                        system_prompt, user_prompt = _shrink_prompts_for_provider(
                            system_prompt[:2000], user_prompt[:3500]
                        )
                        logger.warning(
                            "Timeout → son şans: %s", _active_name or "?"
                        )
                        continue
                    raise RuntimeError(
                        "Tüm model sağlayıcıları yanıt vermedi."
                    ) from exc
                if "model_not_found" in str(exc).lower() or "error code: 404" in str(exc).lower():
                    if _activate_credit_fallback() or (
                        task in ANALYZE_TASKS
                        and _activate_next_analyze_provider(reason="model_not_found")
                    ):
                        continue
                    raise ConfigurationError(
                        f"Model bulunamadı ({_active_name or settings.llm_provider}: "
                        f"{_normalize_groq_model(settings.groq_model) if (_active_name or settings.llm_provider) == 'groq' else settings.active_model}). "
                        "Render'da GROQ_MODEL=llama-3.3-70b-versatile yaz; "
                        "Cerebras anahtarı varsa LLM_FALLBACK=cerebras kalsın."
                    ) from exc
                if _oversized_request(str(exc)):
                    if task in ANALYZE_TASKS and _activate_next_analyze_provider(
                        reason="request_too_large"
                    ):
                        continue
                    raise RuntimeError(
                        "İstek modele sığmadı. Daha kısa bir video dilimiyle tekrar dene."
                    ) from exc

                wait = _retry_after(str(exc))
                if wait is not None:
                    if wait >= RATE_LIMIT_MAX_WAIT:
                        if task in ANALYZE_TASKS and _activate_next_analyze_provider(
                            reason="rate_limit"
                        ):
                            continue
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
                    continue
                if task in ANALYZE_TASKS and _activate_next_analyze_provider(
                    reason="error"
                ):
                    continue
                break
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
        first = failures[0]
        if "timed out" in first.lower() or "timeout" in first.lower() or "gecikti" in first.lower():
            raise RuntimeError("Tüm model sağlayıcıları yanıt vermedi.")
        raise RuntimeError(first)
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
    for result, block in zip(results, chunks):
        chunk_notes = _ground_notes(
            _coerce_notes(result if isinstance(result, dict) else {}),
            block,
        )
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


def _fallback_notes_from_transcript(chunk: str, subject: str | None) -> dict:
    """LLM tamamen düşünce: altyazıdan çalışılabilir not üret (rakip gibi boş dönme)."""
    raw = re.sub(r"\s+", " ", (chunk or "")).strip()
    parts = [
        p.strip()
        for p in re.split(r"(?<=[.!?…])\s+|\n+", raw)
        if len(p.strip()) >= 36 and not _PROMO_NOTE_RE.search(p)
    ]
    if len(parts) < 3:
        # Cümle azsa sabit pencereler.
        step = 180
        parts = [
            raw[i : i + step].strip()
            for i in range(0, min(len(raw), step * 6), step)
            if len(raw[i : i + step].strip()) >= 36
        ]
    notes: list[dict] = []
    topic = (subject or "Ders").strip() or "Ders"
    for index, para in enumerate(parts[:6]):
        title = para[:52].rstrip(" .,;:")
        if len(para) > 52:
            title += "…"
        detail = para
        if len(detail) < 90:
            detail = (
                f"{para} Bu nokta videoda böyle geçiyor; kendi cümlelerinle "
                f"tekrar et ve benzer soruda çeldiriciye dikkat et."
            )
        notes.append(
            {
                "title": title or f"{topic} notu {index + 1}",
                "quote": para[:140],
                "detail": detail[:700],
                "key_points": [para[:100]],
                "mnemonic": f"{topic}: bu cümleyi yüksek sesle 2 kez tekrarla.",
                "exam_tip": "Soru kökünde aynı kavramın tersine çevrilmiş ifadesini ara.",
                "timestamp": index * 40,
            }
        )
    if not notes and raw:
        notes.append(
            {
                "title": f"{topic} — video özeti",
                "quote": raw[:120],
                "detail": raw[:600],
                "key_points": [raw[:80]],
                "mnemonic": f"{topic} videosunu parçalara bölüp tekrar et.",
                "exam_tip": "Altyazıdaki tanımları soru formatında yazarak pekiştir.",
                "timestamp": 0,
            }
        )
    return {
        "notes": notes,
        "questions": [],
        "teacher_persona": {"catchphrases": [], "tone": "öğretici, net"},
    }


def _analyze_combined(
    chunk: str,
    subject: str | None,
    question_count: int,
    exam_target: str | None,
    subject_type: str | None,
    is_yks_fen_question: bool,
    rag_block: str,
    window_label: str = "",
    note_count: int = 8,
) -> dict:
    from app.services.exams import prompt_block

    count = max(3, min(int(question_count or 5), 5))
    notes_wanted = max(5, min(int(note_count or 6), 7))
    # Kısa altyazı = hızlı bitiş; Groq/Gemini timeout'u keser.
    hard_cap = max(3500, min(int(settings.analyze_prompt_chars), 5000))
    work = (chunk or "")[:hard_cap]
    system = (
        NOTES_SYSTEM_PROMPT
        + "\n\nNot ve soruyu AYNI JSON içinde ver. Altyazıda olmayan bilgiyi "
        "not, şık veya açıklamaya yazma. Her not 4-6 cümle: tanım + istisna + "
        "sınav tuzağı. Sadece JSON; markdown yok.\n\n"
        + prompt_block(exam_target)
        + questions_system_for(
            subject_type=subject_type,
            is_yks_fen_question=is_yks_fen_question,
        )
    )
    logger.info("Dilim analiz: %s not/%s soru %s", notes_wanted, count, window_label or "")
    result: dict = {}
    notes: list[dict] = []
    questions: list[dict] = []
    seen: set[str] = set()
    try:
        result = _as_dict(
            _chat(
                system,
                build_combined_analyze_prompt(
                    work,
                    subject,
                    count,
                    exam_target,
                    rag_block,
                    window_label,
                    notes_wanted,
                ),
                temperature=0.1,
                task="analyze",
            )
        )
        notes = _ground_notes(_coerce_notes(result), work)
        _collect([result], questions, seen, count)
        questions = _ground_questions(questions, work)
        if not notes:
            logger.warning("Birleşik analiz boş not; kısa ama zorunlu not denemesi.")
            reset_analyze_provider_chain()
            short = work[:3200]
            result = _as_dict(
                _chat(
                    "Türkçe KPSS notu yaz. Sadece JSON. notes boş olamaz. "
                    "Altyazıda yoksa uydurma. Her not en az 3 cümle. Tanıtım YASAK.",
                    (
                        f"Ders: {subject or 'KPSS'}\nAltyazı:\n{short}\n\n"
                        "En az 4 not yaz. Şema: "
                        '{"notes":[{"title":"...","quote":"...","detail":"...","key_points":["..."],'
                        '"mnemonic":"...","exam_tip":"...","timestamp":0}]}'
                    ),
                    temperature=0.1,
                    task="analyze",
                )
            )
            notes = _ground_notes(_coerce_notes(result), short)
            _collect([result], questions, seen, count)
            questions = _ground_questions(questions, short)
        if not notes:
            raw_notes = [
                note
                for note in _coerce_notes(result)
                if not _is_promo_note(note)
                and (note.get("detail") or note.get("title"))
            ]
            if raw_notes:
                logger.warning("Grounding boş; ham %s not kullanılıyor.", len(raw_notes))
                notes = raw_notes[:10]
        if len(questions) < max(2, count // 2) and notes:
            try:
                more = generate_questions(
                    notes,
                    subject,
                    count,
                    persona=None,
                    exam_target=exam_target,
                    subject_type=subject_type,
                    is_yks_fen_question=is_yks_fen_question,
                )
                _collect([{"questions": more}], questions, seen, count)
            except Exception:
                logger.exception("Dilim soru tamamlaması başarısız")
        if notes:
            persona = merge_personas([result.get("teacher_persona")])
            return {
                "notes": notes,
                "questions": questions,
                "teacher_persona": persona.model_dump(),
            }
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM analiz düştü, altyazı yedeğine geçiliyor: %s", exc)

    # Rakip gibi: kullanıcıya "bekle/bas" demeden her zaman not dön.
    logger.warning("Altyazı yedek notları kullanılıyor (%s).", window_label or "dilim")
    return _fallback_notes_from_transcript(work, subject)


def analyze_slice(
    chunk: str,
    subject: str | None,
    question_count: int,
    exam_target: str | None,
    subject_type: str | None,
    is_yks_fen_question: bool,
    rag_block: str = "",
    window_label: str = "",
    note_count: int = 8,
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
