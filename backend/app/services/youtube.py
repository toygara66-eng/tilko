import html
import json
import logging
import re
from math import ceil
from urllib.parse import parse_qs, urlparse

import httpx
from youtube_transcript_api import YouTubeTranscriptApi


YOUTUBE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
logger = logging.getLogger(__name__)
WATCH_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
PLAYER_URL = (
    "https://www.youtube.com/youtubei/v1/player"
    "?key=AIzaSyB-63vPrdThhKuerbB2N_l7Kwwcxj6yUAc&prettyPrint=false"
)


def extract_video_id(video_url: str) -> str:
    parsed = urlparse(video_url)
    host = (parsed.hostname or "").lower().replace("www.", "")

    if host == "youtu.be":
        candidate = parsed.path.lstrip("/").split("/")[0]
    elif host in {"youtube.com", "m.youtube.com", "music.youtube.com"}:
        if parsed.path == "/watch":
            candidate = parse_qs(parsed.query).get("v", [""])[0]
        elif parsed.path.startswith("/embed/") or parsed.path.startswith("/shorts/"):
            candidate = parsed.path.strip("/").split("/")[1]
        else:
            candidate = ""
    else:
        candidate = ""

    if not YOUTUBE_ID_RE.match(candidate):
        raise ValueError("Geçerli bir YouTube video kimliği bulunamadı.")
    return candidate


def format_timestamp_label(seconds: int) -> str:
    minutes, secs = divmod(max(0, seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:d}:{secs:02d}"


def build_watch_url(video_id: str, seconds: int | None = None) -> str:
    base = f"https://www.youtube.com/watch?v={video_id}"
    if seconds is None:
        return base
    return f"{base}&t={int(seconds)}s"


PREFERRED_LANGUAGES = ["tr", "tr-TR", "en"]


def _snippet_field(snippet, name: str, default):
    if isinstance(snippet, dict):
        return snippet.get(name, default)
    value = getattr(snippet, name, default)
    return default if value is None else value


def normalize_transcript_lines(raw: list | None) -> list[dict] | None:
    if not raw:
        return None
    lines: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").replace("\n", " ").strip()
        if not text:
            continue
        try:
            start = int(float(item.get("start") or 0))
        except (TypeError, ValueError):
            start = 0
        if start < 0:
            start = 0
        lines.append({"start": start, "text": text[:800]})
        if len(lines) >= 20000:
            break
    return lines if len(lines) >= 3 else None


def fetch_transcript_lines(video_id: str) -> list[dict]:
    """Altyazıyı saniye damgasıyla çeker.

    YouTube, Render/Vercel IP'lerini kestiği için önce Gemini/OpenRouter
    (Google videoyu kendisi çeker) denenir.
    """
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

    errors: list[str] = []
    fetchers = (
        (_fetch_via_llm_youtube, 28),
        (_fetch_via_innertube, 8),
    )
    for fetcher, limit in fetchers:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(fetcher, video_id)
            try:
                lines = future.result(timeout=limit)
            except FuturesTimeout:
                errors.append(f"{fetcher.__name__}: timeout")
                continue
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{fetcher.__name__}: {exc}")
                continue
        if lines:
            logger.info("Altyazı %s ile geldi (%s satır)", fetcher.__name__, len(lines))
            return lines
        errors.append(f"{fetcher.__name__}: boş")
    logger.warning("YouTube altyazısı alınamadı %s: %s", video_id, " | ".join(errors))
    raise ValueError(
        "YouTube altyazısı alınamadı. Videoda altyazı (otomatik de olur) açık olsun."
    )


def _fetch_transcript_lines_inner(video_id: str) -> list[dict]:
    api = YouTubeTranscriptApi()
    try:
        transcript = api.fetch(video_id, languages=PREFERRED_LANGUAGES)
    except Exception:
        available = list(api.list(video_id))
        if not available:
            raise ValueError("Bu video için altyazı bulunamadı.")
        transcript = available[0].fetch()

    lines: list[dict] = []
    for snippet in transcript:
        start = int(float(_snippet_field(snippet, "start", 0)))
        text = str(_snippet_field(snippet, "text", "")).replace("\n", " ").strip()
        if text:
            lines.append({"start": start, "text": text})
    return lines


def _pick_caption_track(tracks: list[dict]) -> dict | None:
    if not tracks:
        return None
    for lang in ("tr", "tr-TR"):
        for track in tracks:
            code = str(track.get("languageCode") or "").lower()
            if code == lang.lower() or code.startswith("tr"):
                return track
    return tracks[0]


def _lines_from_json3(payload: dict) -> list[dict]:
    lines: list[dict] = []
    for event in payload.get("events") or []:
        if not isinstance(event, dict):
            continue
        segs = event.get("segs") or []
        text = " ".join(
            str(seg.get("utf8") or "").replace("\n", " ").strip()
            for seg in segs
            if isinstance(seg, dict)
        ).strip()
        if not text:
            continue
        start_ms = event.get("tStartMs") or 0
        lines.append({"start": int(float(start_ms) / 1000), "text": text})
    return lines


def _download_caption(base_url: str, headers: dict | None = None) -> list[dict]:
    url = base_url
    if "fmt=" not in url:
        url += ("&" if "?" in url else "?") + "fmt=json3"
    response = httpx.get(
        url,
        headers=headers
        or {"User-Agent": WATCH_UA, "Accept-Language": "tr-TR,tr;q=0.9"},
        timeout=18,
        follow_redirects=True,
    )
    response.raise_for_status()
    if not response.content:
        raise ValueError("Altyazı boş geldi.")
    lines = _lines_from_caption_bytes(response.content, "json3")
    if lines:
        return lines
    raise ValueError("Altyazı biçimi okunamadı.")


_VTT_STAMP = re.compile(
    r"(?:(\d+):)?(\d{2}):(\d{2})[\.,](\d{3})\s*-->"
)
INVIDIOUS_HOSTS = (
    "https://inv.nadeko.net",
    "https://invidious.nerdvpn.de",
    "https://invidious.f5.si",
    "https://yt.chocolatemoo53.com",
)
_XML_CAPTION = re.compile(
    r'<text[^>]*start="([^"]+)"[^>]*>(.*?)</text>',
    re.IGNORECASE | re.DOTALL,
)


def _vtt_seconds(hour: str | None, minute: str, second: str, millis: str) -> int:
    return int(hour or 0) * 3600 + int(minute) * 60 + int(second)


def _lines_from_vtt(text: str) -> list[dict]:
    lines: list[dict] = []
    blocks = re.split(r"\n\s*\n", (text or "").replace("\r\n", "\n"))
    for block in blocks:
        rows = [
            row.strip()
            for row in block.split("\n")
            if row.strip()
            and not row.strip().startswith("WEBVTT")
            and not row.strip().startswith("NOTE")
            and not row.strip().startswith("Kind:")
            and not row.strip().startswith("Language:")
        ]
        if not rows:
            continue
        stamp: int | None = None
        body: list[str] = []
        for row in rows:
            match = _VTT_STAMP.match(row)
            if match:
                stamp = _vtt_seconds(*match.groups())
                continue
            if row.isdigit():
                continue
            cleaned = re.sub(r"<[^>]+>", "", row).replace("&nbsp;", " ").strip()
            if cleaned:
                body.append(cleaned)
        if stamp is None or not body:
            continue
        lines.append({"start": stamp, "text": " ".join(body)})
    return lines


def _lines_from_xml(raw: str) -> list[dict]:
    lines: list[dict] = []
    for match in _XML_CAPTION.finditer(raw or ""):
        text = re.sub(r"<[^>]+>", "", html.unescape(match.group(2)))
        text = text.replace("\n", " ").strip()
        if not text:
            continue
        lines.append({"start": int(float(match.group(1))), "text": text})
    return lines


def _lines_from_caption_bytes(raw: bytes, ext: str) -> list[dict]:
    if not raw:
        return []
    head = raw.lstrip()[:80]
    kind = (ext or "").lower()
    if head.startswith(b"{") or kind in {"json3", "json", "srv3"}:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict):
            return _lines_from_json3(data)
    if b"<transcript" in head or b"<text" in raw[:400] or kind in {"xml", "srv1", "srv2"}:
        return _lines_from_xml(raw.decode("utf-8", "replace"))
    return _lines_from_vtt(raw.decode("utf-8", "replace"))


def _pick_ytdlp_track(info: dict) -> dict | None:
    bags = (info.get("subtitles") or {}, info.get("automatic_captions") or {})
    preferred = ("tr", "tr-TR", "en", "en-orig", "en-US")
    ranked: list[tuple[int, dict]] = []
    for bag in bags:
        if not isinstance(bag, dict):
            continue
        for lang, tracks in bag.items():
            code = str(lang or "").lower()
            priority = 50
            for index, pref in enumerate(preferred):
                if code == pref.lower() or code.startswith("tr"):
                    priority = index
                    break
            else:
                if code.startswith("en"):
                    priority = 10
            for item in tracks or []:
                if not item.get("url"):
                    continue
                ext = str(item.get("ext") or "")
                bump = 0 if ext == "json3" else 1 if ext in {"vtt", "srv3", "srv1", "ttml"} else 2
                ranked.append((priority * 10 + bump, item))
    if not ranked:
        return None
    ranked.sort(key=lambda row: row[0])
    return ranked[0][1]


def _fetch_via_ytdlp(video_id: str) -> list[dict]:
    import yt_dlp

    watch = f"https://www.youtube.com/watch?v={video_id}"
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "extractor_args": {
            "youtube": {
                "player_client": ["ios", "tv", "web_safari"],
                "skip": ["dash", "hls"],
            }
        },
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(watch, download=False)
        if not info:
            raise ValueError("Video bilgisi alınamadı.")
        track = _pick_ytdlp_track(info)
        if not track:
            raise ValueError("Bu video için altyazı bulunamadı.")
        caption_url = str(track["url"])
        ext = str(track.get("ext") or "json3")
        try:
            response = ydl.urlopen(caption_url)
            raw = response.read()
        except Exception:
            raw = httpx.get(
                caption_url,
                headers={"User-Agent": WATCH_UA, "Accept-Language": "tr-TR,tr;q=0.9"},
                timeout=18,
                follow_redirects=True,
            ).content
    lines = _lines_from_caption_bytes(raw, ext)
    if not lines:
        raise ValueError("Altyazı boş geldi.")
    return lines


def _fetch_via_invidious(video_id: str) -> list[dict]:
    last = "Invidious yanıt vermedi."
    for host in INVIDIOUS_HOSTS:
        try:
            listing = httpx.get(
                f"{host}/api/v1/captions/{video_id}",
                headers={"User-Agent": WATCH_UA},
                timeout=8,
                follow_redirects=True,
            )
            listing.raise_for_status()
            payload = listing.json()
            captions = payload.get("captions") if isinstance(payload, dict) else payload
            if not isinstance(captions, list) or not captions:
                last = f"{host}: liste boş"
                continue
            pick = None
            for lang in ("tr", "en"):
                pick = next(
                    (
                        item
                        for item in captions
                        if str(item.get("languageCode") or "").lower().startswith(lang)
                    ),
                    None,
                )
                if pick:
                    break
            pick = pick or captions[0]
            cap_url = str(pick.get("url") or "")
            if not cap_url:
                last = f"{host}: url yok"
                continue
            if cap_url.startswith("/"):
                cap_url = host + cap_url
            caption = httpx.get(
                cap_url,
                headers={"User-Agent": WATCH_UA, "Accept": "text/vtt, text/plain, */*"},
                timeout=8,
                follow_redirects=True,
            )
            caption.raise_for_status()
            lines = _lines_from_caption_bytes(caption.content, "vtt")
            if lines:
                return lines
            last = f"{host}: dosya boş"
        except Exception as exc:  # noqa: BLE001
            last = f"{host}: {exc}"
    raise ValueError(last)


_IOS_CLIENTS = (
    {
        "client": {
            "clientName": "IOS",
            "clientVersion": "20.10.38",
            "deviceMake": "Apple",
            "deviceModel": "iPhone16,2",
            "osName": "iOS",
            "osVersion": "17.5.1.21F90",
            "hl": "tr",
            "gl": "TR",
        },
        "headers": {
            "User-Agent": "com.google.ios.youtube/20.10.38 (iPhone16,2; U; CPU iOS 17_5_1 like Mac OS X;)",
            "X-YouTube-Client-Name": "5",
            "X-YouTube-Client-Version": "20.10.38",
            "Content-Type": "application/json",
        },
    },
    {
        "client": {
            "clientName": "IOS",
            "clientVersion": "20.10.4",
            "deviceMake": "Apple",
            "deviceModel": "iPhone16,2",
            "osName": "iOS",
            "osVersion": "17.5.1.21F90",
            "hl": "tr",
            "gl": "TR",
        },
        "headers": {
            "User-Agent": "com.google.ios.youtube/20.10.4 (iPhone16,2; U; CPU iOS 17_5_1 like Mac OS X;)",
            "X-YouTube-Client-Name": "5",
            "X-YouTube-Client-Version": "20.10.4",
            "Content-Type": "application/json",
        },
    },
)


def _fetch_via_innertube(video_id: str) -> list[dict]:
    last = "YouTube oynatıcı yanıtı alınamadı."
    for spec in _IOS_CLIENTS:
        try:
            response = httpx.post(
                PLAYER_URL,
                json={
                    "context": {"client": spec["client"]},
                    "videoId": video_id,
                    "contentCheckOk": True,
                    "racyCheckOk": True,
                },
                headers=spec["headers"],
                timeout=16,
                follow_redirects=True,
            )
            response.raise_for_status()
            data = response.json()
            tracks = (
                data.get("captions", {})
                .get("playerCaptionsTracklistRenderer", {})
                .get("captionTracks")
                or []
            )
            track = _pick_caption_track(tracks)
            if not track or not track.get("baseUrl"):
                last = f"{spec['client']['clientVersion']}: altyazı yok"
                continue
            lines = _download_caption(
                str(track["baseUrl"]),
                headers={
                    "User-Agent": spec["headers"]["User-Agent"],
                    "Accept-Language": "tr-TR,tr;q=0.9",
                },
            )
            if lines:
                return lines
            last = f"{spec['client']['clientVersion']}: altyazı boş"
        except Exception as exc:  # noqa: BLE001
            last = str(exc)
    raise ValueError(last)


_STAMP_LINE = re.compile(
    r"^[\[\(]?\s*(?:(\d{1,2}):)?(\d{1,3}):(\d{2})\s*[\]\)]?\s*[-–.]?\s*(.+)$"
)
_STAMP_SECONDS = re.compile(r"^\[(\d+)\]\s*(.+)$")
_TRANSCRIBE_PROMPT = (
    "Bu YouTube ders videosunun konuşmasını Türkçe yazıya dök. "
    "Her satır tam olarak [SANIYE] cümle formatında olsun. "
    "SANIYE tam sayı saniye olsun (dakika:saniye yazma). "
    "Videonun başından sonuna kadar mümkün olduğunca çok satır yaz. "
    "Giriş, özet başlığı veya markdown yazma."
)


def _lines_from_model_transcript(text: str) -> list[dict]:
    lines: list[dict] = []
    for raw in (text or "").splitlines():
        row = raw.strip().lstrip("-* ").strip()
        if not row:
            continue
        sec = _STAMP_SECONDS.match(row)
        if sec:
            body = sec.group(2).strip()
            if body:
                lines.append({"start": int(sec.group(1)), "text": body[:800]})
            continue
        stamp = _STAMP_LINE.match(row)
        if stamp:
            hours, minutes, seconds, body = stamp.groups()
            body = (body or "").strip()
            if not body:
                continue
            total = int(seconds) + int(minutes) * 60 + int(hours or 0) * 3600
            lines.append({"start": total, "text": body[:800]})
    if len(lines) >= 3:
        return lines
    paras = [part.strip() for part in re.split(r"\n+", text or "") if len(part.strip()) > 24]
    if len(paras) < 3:
        return []
    return [{"start": index * 20, "text": part[:800]} for index, part in enumerate(paras[:400])]


def _gemini_text_from_youtube(video_id: str, api_key: str, model: str) -> str:
    watch = f"https://www.youtube.com/watch?v={video_id}"
    response = httpx.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        json={
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": _TRANSCRIBE_PROMPT},
                        {"file_data": {"file_uri": watch}},
                    ],
                }
            ],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 8192},
        },
        timeout=26,
        follow_redirects=True,
    )
    if not response.is_success:
        raise ValueError(f"{model}: {response.status_code} {response.text[:180]}")
    data = response.json()
    chunks: list[str] = []
    for candidate in data.get("candidates") or []:
        parts = ((candidate.get("content") or {}).get("parts")) or []
        chunks.extend(str(part.get("text") or "") for part in parts)
    text = "\n".join(chunk for chunk in chunks if chunk).strip()
    if not text:
        raise ValueError(f"{model}: boş yanıt")
    return text


def _openrouter_text_from_youtube(video_id: str, api_key: str, model: str) -> str:
    watch = f"https://www.youtube.com/watch?v={video_id}"
    response = httpx.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://tilko.site",
            "X-Title": "TILKO",
        },
        json={
            "model": model,
            "temperature": 0.1,
            "max_tokens": 8192,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _TRANSCRIBE_PROMPT},
                        {"type": "image_url", "image_url": {"url": watch}},
                    ],
                }
            ],
        },
        timeout=26,
        follow_redirects=True,
    )
    if not response.is_success:
        raise ValueError(f"openrouter {model}: {response.status_code} {response.text[:180]}")
    data = response.json()
    choices = data.get("choices") or []
    if not choices:
        raise ValueError("openrouter boş yanıt")
    message = (choices[0].get("message") or {}).get("content") or ""
    if isinstance(message, list):
        message = " ".join(
            str(part.get("text") or "") for part in message if isinstance(part, dict)
        )
    text = str(message).strip()
    if not text:
        raise ValueError("openrouter boş metin")
    return text


def _fetch_via_llm_youtube(video_id: str) -> list[dict]:
    from app.config import settings

    errors: list[str] = []
    gemini_key = (settings.gemini_api_key or "").strip()
    if gemini_key:
        models = []
        preferred = (settings.gemini_model or "").strip()
        for name in (preferred, "gemini-2.5-flash", "gemini-2.0-flash", "gemini-3.6-flash"):
            if name and name not in models:
                models.append(name)
        for model in models:
            try:
                text = _gemini_text_from_youtube(video_id, gemini_key, model)
                lines = _lines_from_model_transcript(text)
                if lines:
                    return lines
                errors.append(f"{model}: satır yok")
            except Exception as exc:  # noqa: BLE001
                errors.append(str(exc))

    openrouter_key = (settings.openrouter_api_key or "").strip()
    if openrouter_key:
        models = []
        for name in (
            "google/gemini-2.5-flash",
            (settings.openrouter_model or "").strip(),
            "google/gemini-2.0-flash-001",
        ):
            if name and name.startswith("google/") and name not in models:
                models.append(name)
        for model in models:
            try:
                text = _openrouter_text_from_youtube(video_id, openrouter_key, model)
                lines = _lines_from_model_transcript(text)
                if lines:
                    return lines
                errors.append(f"{model}: satır yok")
            except Exception as exc:  # noqa: BLE001
                errors.append(str(exc))

    raise ValueError(" | ".join(errors) or "LLM ile altyazı alınamadı.")


def _fetch_via_gemini_youtube(video_id: str) -> list[dict]:
    return _fetch_via_llm_youtube(video_id)


def _fetch_via_watch_html(video_id: str) -> list[dict]:
    watch = httpx.get(
        f"https://www.youtube.com/watch?v={video_id}&hl=tr",
        headers={"User-Agent": WATCH_UA, "Accept-Language": "tr-TR,tr;q=0.9"},
        timeout=18,
        follow_redirects=True,
    )
    watch.raise_for_status()
    match = re.search(r"ytInitialPlayerResponse\s*=\s*(\{.+?\});\s*(?:var|</script>)", watch.text)
    if not match:
        raise ValueError("YouTube oynatıcı yanıtı okunamadı.")
    data = json.loads(match.group(1))
    tracks = (
        data.get("captions", {})
        .get("playerCaptionsTracklistRenderer", {})
        .get("captionTracks")
        or []
    )
    track = _pick_caption_track(tracks)
    if not track or not track.get("baseUrl"):
        raise ValueError("Bu video için altyazı bulunamadı.")
    return _download_caption(str(track["baseUrl"]))


def transcript_as_prompt_block(lines: list[dict]) -> str:
    return "\n".join(f"[{item['start']}] {item['text']}" for item in lines if item["text"])


def chunk_transcript(lines: list[dict], max_chars: int = 24000) -> list[str]:
    """Uzun altyazıyı parçalara böler.

    Parça sınırı bilinçli olarak büyük: her parça bir LLM isteği demek ve ücretsiz
    kotalar istek sayısına göre sayılıyor. Modelin bağlamı bu boyutu rahat kaldırıyor.
    """
    chunks: list[str] = []
    current: list[dict] = []
    size = 0
    for item in lines:
        if not item["text"]:
            continue
        entry_size = len(item["text"]) + 12
        if current and size + entry_size > max_chars:
            chunks.append(transcript_as_prompt_block(current))
            current = []
            size = 0
        current.append(item)
        size += entry_size
    if current:
        chunks.append(transcript_as_prompt_block(current))
    return chunks


def slice_transcript(lines: list[dict], window_seconds: int = 300) -> list[dict]:
    """Altyazıyı 5 dakikalık dilimlere böler: [{start, end, label, block}]."""
    usable = [item for item in lines if item.get("text")]
    if not usable:
        return []
    end_at = max(int(item.get("start") or 0) for item in usable) + 1
    slices: list[dict] = []
    start = 0
    while start < end_at:
        stop = start + window_seconds
        piece = [
            item
            for item in usable
            if start <= int(item.get("start") or 0) < stop
        ]
        if piece:
            last = int(piece[-1].get("start") or start)
            slices.append(
                {
                    "start": start,
                    "end": last,
                    "label": f"{format_timestamp_label(start)}–{format_timestamp_label(min(stop, last + 1))}",
                    "block": transcript_as_prompt_block(piece),
                }
            )
        start = stop
    return slices


def compact_transcript(lines: list[dict], max_chars: int = 28000) -> str:
    """Tüm videoyu kapsa: sığmazsa satır atlayarak baş-orta-sonu koru."""
    usable = [item for item in lines if item.get("text")]
    if not usable:
        return ""
    full = transcript_as_prompt_block(usable)
    if len(full) <= max_chars:
        return full
    step = max(1, ceil(len(full) / max_chars))
    sampled = usable[::step]
    if sampled[-1] is not usable[-1]:
        sampled.append(usable[-1])
    out = transcript_as_prompt_block(sampled)
    while len(out) > max_chars and step < len(usable):
        step += 1
        sampled = usable[::step]
        if sampled[-1] is not usable[-1]:
            sampled.append(usable[-1])
        out = transcript_as_prompt_block(sampled)
    return out


def transcript_duration_seconds(lines: list[dict]) -> int:
    if not lines:
        return 0
    return max(int(item.get("start") or 0) for item in lines)
