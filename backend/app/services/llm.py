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
# Ücretli Gemini: yeterince bekle. 40sn acele timeout → sessiz Groq (AI Studio kullanım 0).
ANALYZE_HTTP_TIMEOUT = httpx.Timeout(75.0, connect=12.0)
GEMINI_ANALYZE_TIMEOUT = httpx.Timeout(75.0, connect=12.0)
ANALYZE_TASKS = frozenset({"analyze", "notes", "questions"})
ANALYZE_FAST_MODEL = "nvidia/nemotron-3-nano-30b-a3b:free"
GEMINI_CHAT_MODEL = "gemini-3.5-flash-lite"
# Birincil = ayardaki model; eski 2.x yeni anahtarlarda 404.
GEMINI_MODEL_FALLBACKS = (
    "gemini-3.5-flash-lite",
    "gemini-3.6-flash",
    "gemini-flash-latest",
)
GEMINI_UNAVAILABLE_MODELS = frozenset(
    {
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash",
        "gemini-2.5-pro",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-1.5-pro",
        "gemini-1.5-pro-latest",
        "gemini-1.5-flash",
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
# Teşhis: AI Studio'da kullanım yoksa hangi sağlayıcı cevap verdi?
_llm_stats: dict[str, object] = {
    "last_ok_provider": "",
    "last_ok_model": "",
    "last_error": "",
    "last_gemini_error": "",
    "gemini_ok": 0,
    "gemini_fail": 0,
    "fallback_ok": 0,
}
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
        tip = _pick_note_field(item, "exam_tip", "uyari", "uyarı", "warning")
        cleaned = {
            **item,
            "title": title or detail[:48],
            "detail": detail or title,
        }
        if tip and (_JUNK_NOTE_RE.search(tip) or _SYSTEM_TIP_RE.search(tip)):
            cleaned["exam_tip"] = ""
        else:
            cleaned["exam_tip"] = tip
        if _is_junk_note(cleaned):
            continue
        notes.append(cleaned)
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

_JUNK_NOTE_RE = re.compile(
    r"("
    r"hourly\s*limit|free\s*model\s*usage|upgrade\s*to\s*a\s*paid|"
    r"cannot\s*provide|don'?t\s*have\s*(enough\s*)?context|"
    r"not\s*part\s*of\s*my\s*knowledge|knowledge\s*base|"
    r"as\s*an\s*ai|i\s*cannot|i\s*don'?t\s*have|"
    r"try\s*again\s*later|rate[\s-]*limit|"
    r"videoya?\s*(erişemiyorum|ulaşamıyorum)|bağlam\s*(yetersiz|yok)|"
    r"bilgim\s*(dahil|yok)|genel\s*bilgi\s*verebilirim|"
    r"altyazı\s*(sağlanmadı|yok)|transkript\s*yok|"
    # Model/sistem hatası not olarak basılmasın
    r"çalışılabilir\s*not\s*yazamad[ıi]|model\s*bu\s*dilimde|"
    r"başka\s*bölüm\s*veya\s*(video|altyazılı)|"
    r"yeterli\s*altyazı\s*(yok|bulunamadı)|"
    # Meta / şablon not (gerçek ders içeriği değil)
    r"için\s*hazırlanan\s*çalışma\s*notu|"
    r"dersi\s*için\s*hazırlanan|"
    r"bu\s*çalışma\s*notu\s*,?\s*.{0,40}dersinin|"
    r"analiz\s*şu\s*an\s*(yoğun|tamamlanamadı)"
    r")",
    re.IGNORECASE,
)

_SYSTEM_TIP_RE = re.compile(
    r"("
    r"çalışılabilir\s*not|model\s*bu\s*dilimde|"
    r"başka\s*bölüm\s*veya|yeterli\s*altyazı|"
    r"hourly\s*limit|rate[\s-]*limit|i\s*cannot|"
    r"try\s*again\s*later|analiz\s*şu\s*an"
    r")",
    re.IGNORECASE,
)

_FILLER_TRANSCRIPT_RE = re.compile(
    r"("
    r"gitti\s+geliyor|geldi\s+gitti|ne\s+yapsak|ne\s+etsek|"
    r"bakalım\s+görelim|olsa\s+olsa|yapsak\s+etsek|"
    r"şöyle\s+böyle|ee+\s|ıı+\s|hmm+"
    r")",
    re.IGNORECASE,
)

_EDU_SIGNAL_RE = re.compile(
    r"("
    r"\b(eki|ekler|kök|gövde|tamlama|fiil|isim|sıfat|zarf|"
    r"edat|bağlaç|yapım|çekim|ülama|ünsüz|"
    r"madde|anayasa|meşrutiyet|osmanlı|inkılap|cumhuriyet|"
    r"coğrafya|iklim|nüfus|harita|"
    r"denklem|oran|yüzde|üçgen|alan|çevre|kesir|"
    r"tanım|istisna|kural|çeldirici|ösym|kpss|yks|"
    r"öncül|hipotez|teorem|formül|"
    r"ünite|konu|örnek|açıkla|ders|öğret|kavram|özet)\b"
    r")",
    re.IGNORECASE,
)


def _note_blob(note: dict) -> str:
    return " ".join(
        [
            str(note.get("title") or ""),
            str(note.get("detail") or ""),
            str(note.get("text") or ""),
            str(note.get("quote") or ""),
            str(note.get("mnemonic") or ""),
            str(note.get("exam_tip") or ""),
            " ".join(str(p) for p in (note.get("key_points") or [])),
        ]
    )


def _is_thin_note(note: dict) -> bool:
    """İskelet / boş not — banko sınav notu sayılmaz (kısa ama dolu not OK)."""
    detail = str(note.get("detail") or note.get("text") or "").strip()
    points = [str(p).strip() for p in (note.get("key_points") or []) if str(p).strip()]
    tip = str(note.get("exam_tip") or "").strip()
    title = str(note.get("title") or "").strip()
    substance = len(detail) + sum(len(p) for p in points) + len(tip)
    if len(points) >= 3 and substance >= 90:
        return False
    if len(detail) >= 40 and len(points) >= 2:
        return False
    if substance < 90 and len(points) < 3:
        return True
    if len(detail) < 24 and len(points) < 2:
        return True
    if detail and title and detail.casefold() == title.casefold() and len(points) < 2:
        return True
    return False


def _is_junk_note(note: dict) -> bool:
    blob = _note_blob(note)
    if not blob.strip():
        return True
    if _JUNK_NOTE_RE.search(blob):
        return True
    if _is_promo_note(note):
        return True
    title = str(note.get("title") or "").strip()
    detail = str(note.get("detail") or note.get("text") or "").strip()
    tip = str(note.get("exam_tip") or "").strip()
    if tip and _SYSTEM_TIP_RE.search(tip):
        note["exam_tip"] = ""
        tip = ""
    # Ham altyazı tekrarı / boş sohbet
    if _FILLER_TRANSCRIPT_RE.search(title) and not _EDU_SIGNAL_RE.search(blob):
        return True
    points = [str(p).strip() for p in (note.get("key_points") or []) if str(p).strip()]
    if len(detail) < 40 and len(points) < 2 and not _EDU_SIGNAL_RE.search(blob):
        return True
    # Aynı kelimeyi 4+ kez tekrarlayan çöp
    words = re.findall(r"[A-Za-zÇĞİÖŞÜçğıöşü]{3,}", blob.lower())
    if words:
        top = max(words.count(w) for w in set(words))
        if top >= 6 and len(set(words)) < 12:
            return True
    return False


def _sanitize_note_tips(notes: list[dict]) -> list[dict]:
    """Sistem hatası / meta exam_tip'leri temizle."""
    out: list[dict] = []
    for note in notes:
        if not isinstance(note, dict):
            continue
        tip = str(note.get("exam_tip") or "")
        if tip and (_SYSTEM_TIP_RE.search(tip) or _JUNK_NOTE_RE.search(tip)):
            note = {**note, "exam_tip": ""}
        if _is_junk_note(note):
            continue
        out.append(note)
    return out


def _filter_quality_notes(notes: list[dict], *, require_depth: bool = False) -> list[dict]:
    out: list[dict] = []
    for note in notes:
        if not isinstance(note, dict) or _is_junk_note(note):
            continue
        if require_depth and _is_thin_note(note):
            continue
        out.append(note)
    return out


def _clip_at_word(text: str, max_len: int) -> str:
    clean = re.sub(r"\s+", " ", (text or "").strip())
    if len(clean) <= max_len:
        return clean
    cut = clean[:max_len].rstrip(" .…,;:")
    space = cut.rfind(" ")
    if space > max_len * 0.55:
        cut = cut[:space]
    return cut.rstrip(" .…,;:")


def _compact_exam_notes(notes: list[dict]) -> list[dict]:
    """Uzun kompozisyonu 100'lük öğrenci defteri formatına sıkıştır."""
    out: list[dict] = []
    for raw in notes:
        if not isinstance(raw, dict):
            continue
        note = dict(raw)
        detail = str(note.get("detail") or note.get("text") or "").strip()
        points = [str(p).strip() for p in (note.get("key_points") or []) if str(p).strip()]
        if len(points) < 3 and detail:
            sents = [
                s.strip()
                for s in re.split(r"(?<=[.!?…])\s+", detail)
                if len(s.strip()) >= 12
            ]
            for sent in sents:
                if len(points) >= 6:
                    break
                chunk = _clip_at_word(sent, 90)
                if chunk and chunk not in points:
                    points.append(chunk)
        if len(detail) > 180:
            sents = [s.strip() for s in re.split(r"(?<=[.!?…])\s+", detail) if s.strip()]
            detail = " ".join(sents[:3])
            detail = _clip_at_word(detail, 180)
        note["detail"] = detail
        note["text"] = detail
        note["key_points"] = [_clip_at_word(p, 90) for p in points[:6]]
        tip = str(note.get("exam_tip") or "").strip()
        if tip:
            tip_sents = re.split(r"(?<=[.!?…])\s+", tip)
            note["exam_tip"] = _clip_at_word(tip_sents[0].strip(), 120)
        mnemonic = str(note.get("mnemonic") or "").strip()
        if mnemonic:
            note["mnemonic"] = _clip_at_word(mnemonic, 120)
        out.append(note)
    return out


def _expand_thin_notes(
    notes: list[dict],
    transcript: str,
    subject: str | None,
) -> list[dict]:
    """İskelet kalan notları banko sınav maddelerine çevir."""
    thin = [n for n in notes if _is_thin_note(n)]
    if not thin:
        return notes
    compact = []
    for note in thin[:6]:
        compact.append(
            {
                "title": note.get("title") or "",
                "quote": note.get("quote") or "",
                "detail": note.get("detail") or note.get("text") or "",
                "key_points": note.get("key_points") or [],
                "timestamp": note.get("timestamp") or 0,
            }
        )
    try:
        result = _as_dict(
            _chat(
                "Türkçe KPSS sınav notu yazarısın. İskelet notları 100'lük öğrenci "
                "defteri formatına ÇEVİR: kısa detail + 4-6 banko madde. "
                "Uzun kompozisyon YASAK. Altyazıda olmayanı uydurma. Sadece JSON.",
                (
                    f"Ders: {subject or 'KPSS'}\n"
                    f"Altyazı:\n{(transcript or '')[:4500]}\n\n"
                    f"İskelet notlar (bankola):\n{json.dumps(compact, ensure_ascii=False)}\n\n"
                    "Her not: detail 1-3 kısa cümle (~40-180 karakter); "
                    "key_points 4-6 bitmiş madde (her biri max ~90 karakter). "
                    "Cümleyi '...' ile kesme. Şema: "
                    '{"notes":[{"title":"...","quote":"...","detail":"...","key_points":["..."],'
                    '"mnemonic":"...","exam_tip":"...","timestamp":0}]}'
                ),
                temperature=0.15,
                task="notes",
            )
        )
        expanded = _ground_notes(_coerce_notes(result), transcript)
        if not expanded:
            expanded = _filter_quality_notes(_coerce_notes(result))
        if not expanded:
            return notes
        by_title = {
            _fold_tr(str(n.get("title") or "")): n for n in expanded if n.get("title")
        }
        merged: list[dict] = []
        for note in notes:
            key = _fold_tr(str(note.get("title") or ""))
            richer = by_title.get(key)
            if richer and not _is_thin_note(richer):
                merged.append({**note, **richer})
            elif not _is_thin_note(note):
                merged.append(note)
            elif richer:
                merged.append({**note, **richer})
            else:
                merged.append(note)
        for key, richer in by_title.items():
            if key and all(_fold_tr(str(n.get("title") or "")) != key for n in merged):
                if not _is_thin_note(richer):
                    merged.append(richer)
        return _compact_exam_notes(merged or notes)
    except Exception:  # noqa: BLE001
        logger.exception("Kısa not genişletme başarısız")
        return notes


def _is_promo_note(note: dict) -> bool:
    blob = _note_blob(note)
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
        if _is_junk_note(note):
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
        return _filter_quality_notes(kept)
    # Model quote'u bozsa bile ders notunu tamamen düşürme.
    soft = [
        note
        for note in notes
        if not _is_junk_note(note)
        and len(str(note.get("detail") or note.get("title") or "").strip()) >= 48
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
    # Render'da kalan GEMINI_MODEL=gemini-2.5-flash-lite → yeni anahtarlarda 404.
    if raw in GEMINI_UNAVAILABLE_MODELS:
        logger.warning(
            "GEMINI_MODEL=%s yeni kullanıcılar için kapalı; %s kullanılıyor.",
            raw,
            GEMINI_CHAT_MODEL,
        )
        return GEMINI_CHAT_MODEL
    return raw


def _gemini_models_to_try() -> list[str]:
    """Analizde tek model (2×40 sn beklemeyi kes); diğer işlerde 1 yedek."""
    primary = _gemini_model_id()
    task = usage_task.get() or ""
    if task in ANALYZE_TASKS:
        if primary and primary not in GEMINI_UNAVAILABLE_MODELS:
            return [primary]
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


def _is_gemini_openai_client(client: OpenAI) -> bool:
    """Gemini'nin OpenAI-uyumlu uç noktası (native generateContent değil)."""
    base = str(getattr(client, "base_url", "") or "")
    return "generativelanguage.googleapis.com" in base and "/openai" in base


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
        task = usage_task.get() or ""
        # Ücretli Gemini: detaylı not için yeterli çıktı tavanı.
        if task in ANALYZE_TASKS:
            out_tokens = 4096 if index == 0 else 2800
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
                _record_llm_fail("gemini", exc)
                # Analizde ikinci modele gitme — hemen yedek sağlayıcı.
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
                _record_llm_fail("gemini", last)
                raise ConfigurationError(
                    "GEMINI_API_KEY geçersiz veya yetkisiz (401/403). "
                    "Render'daki anahtarın Google AI Studio'daki ücretli proje anahtarıyla aynı olduğundan emin ol."
                ) from last
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
        _record_llm_ok("gemini", name)
        return _as_chat_response(text, name)
    if last and _is_timeout(last):
        _record_llm_fail("gemini", last)
        raise TimeoutError(str(last) or "Gemini timed out") from last
    _record_llm_fail("gemini", last or "Gemini yanıt vermedi")
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
    """Groq 8K TPM dar; ücretli Gemini'de promptu budama."""
    name = (_active_name or settings.llm_provider or "").strip().lower()
    task = usage_task.get() or ""
    system = system_prompt
    user = user_prompt
    if name == "gemini" or (task in ANALYZE_TASKS and name in {"", "gemini"}):
        # Gemini: hafif tavan, kaliteyi bozma.
        if len(system) > 4000:
            system = system[:4000] + "\n...(kısaltıldı)"
        if len(user) > 9000:
            user = user[:9000] + "\n...(altyazı kısaltıldı)"
        return system, user
    if task in ANALYZE_TASKS and name in {"groq", "cerebras"}:
        sys_cap, user_cap = (1800, 3000) if name == "groq" else (2200, 3800)
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


def _record_llm_ok(provider: str, model: str = "") -> None:
    name = (provider or "").strip().lower() or "?"
    with _provider_lock:
        _llm_stats["last_ok_provider"] = name
        _llm_stats["last_ok_model"] = (model or "")[:80]
        _llm_stats["last_error"] = ""
        if name == "gemini":
            _llm_stats["gemini_ok"] = int(_llm_stats.get("gemini_ok") or 0) + 1
            _llm_stats["last_gemini_error"] = ""
        else:
            _llm_stats["fallback_ok"] = int(_llm_stats.get("fallback_ok") or 0) + 1


def _record_llm_fail(provider: str, exc: Exception | str) -> None:
    name = (provider or "").strip().lower() or "?"
    msg = str(exc)[:240]
    with _provider_lock:
        _llm_stats["last_error"] = f"{name}: {msg}"
        if name == "gemini":
            _llm_stats["gemini_fail"] = int(_llm_stats.get("gemini_fail") or 0) + 1
            _llm_stats["last_gemini_error"] = msg


def _prefer_gemini_strict() -> bool:
    """Ücretli Gemini tercih ediliyorsa acele Groq'a düşme."""
    return (settings.llm_provider or "").strip().lower() == "gemini" and bool(
        (settings.gemini_api_key or "").strip()
    )


def probe_gemini() -> dict[str, object]:
    """Küçük bir istek at; AI Studio anahtarının gerçekten çalışıp çalışmadığını göster."""
    key = (settings.gemini_api_key or "").strip()
    model = _gemini_model_id()
    if not key:
        return {"ok": False, "via": "", "model": model, "error": "GEMINI_API_KEY yok"}
    openai_err = ""
    # 1) OpenAI-uyumlu uç
    try:
        client = _openai_client(
            api_key=key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            timeout=httpx.Timeout(25.0, connect=10.0),
        )
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": 'Sadece JSON yaz: {"ping":true}'}],
            temperature=0,
            max_tokens=40,
        )
        text = str(response.choices[0].message.content or "")[:120]
        _record_llm_ok("gemini", model)
        return {"ok": True, "via": "openai-compatible", "model": model, "sample": text, "error": ""}
    except Exception as openai_exc:  # noqa: BLE001
        openai_err = str(openai_exc)[:300]
    # 2) Native generateContent
    try:
        raw = _gemini_native_completion(
            [{"role": "user", "content": 'Sadece JSON yaz: {"ping":true}'}],
            temperature=0,
            json_mode=True,
        )
        text = str(raw.choices[0].message.content or "")[:120]
        return {"ok": True, "via": "native", "model": model, "sample": text, "error": ""}
    except Exception as native_exc:  # noqa: BLE001
        native_err = str(native_exc)[:300]
        _record_llm_fail("gemini", native_err)
        return {
            "ok": False,
            "via": "",
            "model": model,
            "error": f"openai={openai_err} | native={native_err}",
        }


def analyze_llm_ready() -> dict[str, bool | str | int]:
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
    with _provider_lock:
        stats = dict(_llm_stats)
    return {
        "gemini": gemini,
        "nebius": nebius,
        "groq": groq,
        "cerebras": cerebras,
        "ready": ready,
        "provider": provider or settings.llm_provider,
        "model": model,
        "last_ok_provider": str(stats.get("last_ok_provider") or ""),
        "last_ok_model": str(stats.get("last_ok_model") or ""),
        "last_error": str(stats.get("last_error") or ""),
        "last_gemini_error": str(stats.get("last_gemini_error") or ""),
        "gemini_ok": int(stats.get("gemini_ok") or 0),
        "gemini_fail": int(stats.get("gemini_fail") or 0),
        "fallback_ok": int(stats.get("fallback_ok") or 0),
        "gemini_key_suffix": (settings.gemini_api_key or "")[-4:] if gemini else "",
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
    """Analiz: ücretli Gemini önce (kalite), sonra hızlı yedekler."""
    preferred = (settings.llm_provider or "gemini").strip().lower()
    quality_first = ["gemini", "groq", "cerebras", "nebius"]
    if preferred == "openrouter":
        return ["openrouter", *quality_first]
    if preferred == "ollama":
        return ["ollama"]
    if preferred in {"gemini", "groq", "cerebras", "nebius"}:
        return [preferred] + [n for n in quality_first if n != preferred]
    return list(quality_first)


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
        if (_active_name or settings.llm_provider or "").lower() == "groq":
            kwargs["max_tokens"] = 900
        elif (_active_name or settings.llm_provider or "").lower() == "gemini":
            kwargs["max_tokens"] = 4096
        else:
            kwargs["max_tokens"] = 2200
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
    # Gemini OpenAI-uyumlu client: SDK yolu kullan (native'e zorlama — asıl hata kaynağı buydu).
    if _is_gemini_openai_client(client):
        try:
            response = client.chat.completions.create(**kwargs)
            _record_llm_ok("gemini", str(kwargs.get("model") or ""))
            return response
        except Exception as exc:
            logger.warning("Gemini OpenAI-uyumlu düştü, native denenecek: %s", exc)
            _record_llm_fail("gemini", exc)
            return _gemini_native_completion(messages, temperature, json_mode)
    if _is_gemini_client(client) or (
        str(model or "").startswith("gemini-") and not _is_gemini_openai_client(client)
    ):
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
    gemini_timeouts = 0
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
                active = (_active_name or settings.llm_provider or "").strip().lower()
                if active and active != "gemini":
                    # Gerçek model adını mümkünse yanıt/istemciden al.
                    model_name = ""
                    try:
                        pair = _named_client(active)
                        model_name = str((pair or (None, ""))[1] or "")
                    except Exception:  # noqa: BLE001
                        model_name = ""
                    _record_llm_ok(active, model_name or settings.active_model)
                return answer
            except ServiceBusyError:
                raise
            except FatalLLMError:
                raise
            except Exception as exc:
                fatal = _fatal_message(str(exc))
                if fatal:
                    # Gemini anahtarı bozuksa ücretsiz yedeğe düşüp "kullanım yok" yanıltmasın.
                    if (
                        _prefer_gemini_strict()
                        and ("401" in str(exc) or "403" in str(exc) or "yetkisiz" in fatal.lower())
                    ):
                        raise ConfigurationError(fatal) from exc
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
                    # Ücretli Gemini: 2 kez aynı sağlayıcıda dene, sonra yedek.
                    if (
                        task in ANALYZE_TASKS
                        and _prefer_gemini_strict()
                        and not _skip_gemini
                        and (_active_name or "gemini") == "gemini"
                        and gemini_timeouts < 2
                    ):
                        gemini_timeouts += 1
                        logger.warning(
                            "Gemini timeout; yeniden denenecek (%s/2).",
                            gemini_timeouts,
                        )
                        time.sleep(1.5)
                        continue
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
    notes = _compact_exam_notes(_sanitize_note_tips(_filter_quality_notes(notes) or notes))
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
    """LLM düşünce: yalnızca eğitim sinyalli altyazı parçalarından az sayıda not."""
    raw = re.sub(r"\s+", " ", (chunk or "")).strip()
    empty = {
        "notes": [],
        "questions": [],
        "teacher_persona": {"catchphrases": [], "tone": "öğretici, net"},
    }
    if len(raw) < 80:
        return empty

    parts = [
        p.strip()
        for p in re.split(r"(?<=[.!?…])\s+|\n+", raw)
        if len(p.strip()) >= 55
        and not _PROMO_NOTE_RE.search(p)
        and not _FILLER_TRANSCRIPT_RE.search(p)
        and not _JUNK_NOTE_RE.search(p)
        and _EDU_SIGNAL_RE.search(p)
    ]
    if len(parts) < 2:
        return empty

    notes: list[dict] = []
    topic = (subject or "Ders").strip() or "Ders"
    for index, para in enumerate(parts[:3]):
        title_words = [w for w in para.split() if len(w) > 2][:6]
        title = " ".join(title_words).rstrip(" .,;:")
        if len(title) < 8:
            title = f"{topic} — nokta {index + 1}"
        # Şablon cümle ekleme; sadece altyazı + kısa çalışma yönü.
        detail = _clip_at_word(para, 160)
        note = {
            "title": title[:72],
            "quote": _clip_at_word(para, 120),
            "detail": detail,
            "key_points": [
                _clip_at_word(para, 90),
                "Aynı ifade soru kökünde tersine çevrilebilir",
            ],
            "mnemonic": f"{topic}: bu cümleyi 2 kez tekrarla.",
            "exam_tip": "Soru kökünde aynı kavramın tersine çevrilmiş ifadesini ara.",
            "timestamp": index * 40,
        }
        if _is_junk_note(note):
            continue
        notes.append(note)

    return {
        "notes": _sanitize_note_tips(notes),
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

    count = max(4, min(int(question_count or 5), 6))
    notes_wanted = max(4, min(int(note_count or 6), 7))
    # Ücretli Gemini: daha zengin bağlam.
    hard_cap = max(7000, min(int(settings.analyze_prompt_chars), 12000))
    work = (chunk or "")[:hard_cap]
    system = (
        NOTES_SYSTEM_PROMPT
        + "\n\nNot ve soruyu AYNI JSON içinde ver. Altyazıda olmayan bilgiyi "
        "not, şık veya açıklamaya yazma. 100'lük öğrenci defteri: her not "
        "1-3 kısa cümle detail + 4-6 banko madde; uzun kompozisyon YASAK; "
        "cümleyi '...' ile kesme. Sadece JSON; markdown yok.\n\n"
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
                temperature=0.15,
                task="analyze",
            )
        )
        notes = _ground_notes(_coerce_notes(result), work)
        _collect([result], questions, seen, count)
        questions = _ground_questions(questions, work)
        if not notes:
            logger.warning("Birleşik analiz boş not; derin not denemesi.")
            reset_analyze_provider_chain()
            short = work[:4500]
            result = _as_dict(
                _chat(
                    "Türkçe KPSS banko sınav notu yaz. Sadece JSON. notes boş olamaz. "
                    "Altyazıda yoksa uydurma. Her not: 1-3 kısa cümle + 4-6 madde. "
                    "Uzun paragraf YASAK. Tanıtım YASAK. İngilizce uyarı / kota / 'I cannot' YASAK.",
                    (
                        f"Ders: {subject or 'KPSS'}\nAltyazı:\n{short}\n\n"
                        "5-7 banko not yaz. Şema: "
                        '{"notes":[{"title":"...","quote":"...","detail":"...","key_points":["..."],'
                        '"mnemonic":"...","exam_tip":"...","timestamp":0}]}'
                    ),
                    temperature=0.15,
                    task="analyze",
                )
            )
            notes = _ground_notes(_coerce_notes(result), short)
            _collect([result], questions, seen, count)
            questions = _ground_questions(questions, short)
        if not notes:
            raw_notes = _filter_quality_notes(
                [
                    note
                    for note in _coerce_notes(result)
                    if note.get("detail") or note.get("title")
                ]
            )
            if raw_notes:
                logger.warning("Grounding boş; ham %s kaliteli not kullanılıyor.", len(raw_notes))
                notes = raw_notes[:8]
        if not notes:
            # Son yumuşak kabul: sistem çöpü değilse sınav değeri olan notları tut.
            soft = []
            for note in _coerce_notes(result):
                detail = str(note.get("detail") or note.get("text") or "").strip()
                points = [
                    str(p).strip()
                    for p in (note.get("key_points") or [])
                    if str(p).strip()
                ]
                if len(detail) < 36 and len(points) < 2:
                    continue
                if _JUNK_NOTE_RE.search(_note_blob(note)):
                    continue
                soft.append(note)
            if soft:
                logger.warning("Yumuşak kabul: %s not.", len(soft))
                notes = soft[:8]
        notes = _sanitize_note_tips(_filter_quality_notes(notes) or notes)
        notes = _compact_exam_notes(notes)
        # İskelet kalanları bankola; silinirse önceki notları koru.
        if notes and sum(1 for n in notes if _is_thin_note(n)) >= max(1, len(notes) // 2):
            logger.warning("Notlar iskelet kaldı; banko sıkıştırma turu.")
            before = list(notes)
            try:
                notes = _expand_thin_notes(notes, work, subject)
                notes = _compact_exam_notes(
                    _sanitize_note_tips(_filter_quality_notes(notes)) or before
                )
            except Exception:  # noqa: BLE001
                notes = before
        # Sorular: birleşik JSON'dan gelen + gerekirse kısa ek üretim (max 25 sn).
        if notes and len(questions) < max(2, count // 2):
            from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

            try:
                with ThreadPoolExecutor(max_workers=1) as pool:
                    fut = pool.submit(
                        generate_questions,
                        notes,
                        subject,
                        count,
                        None,
                        exam_target,
                        subject_type,
                        is_yks_fen_question,
                    )
                    more = fut.result(timeout=25)
                _collect([{"questions": more}], questions, seen, count)
            except FuturesTimeout:
                logger.warning("Soru üretimi zaman aşımı; notlarla devam.")
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

    # Kaliteli yedek yoksa çöp basma — temiz hata ver.
    logger.warning("Altyazı yedek notları deneniyor (%s).", window_label or "dilim")
    fallback = _fallback_notes_from_transcript(work, subject)
    fallback_notes = _sanitize_note_tips(list(fallback.get("notes") or []))
    if fallback_notes:
        fallback["notes"] = fallback_notes
        return fallback
    raise RuntimeError(
        "Bu videodan anlamlı ders notu çıkarılamadı. "
        "Altyazılı, ders anlatımlı bir bölüm dene."
    )


def quick_transcript_notes(chunk: str, subject: str | None = None) -> dict:
    """UI boş kalmasın diye LLM öncesi anında not."""
    return _fallback_notes_from_transcript(chunk or "", subject)


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
