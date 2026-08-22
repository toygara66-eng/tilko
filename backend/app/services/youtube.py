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
PLAYER_URL = "https://www.youtube.com/youtubei/v1/player"


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


def fetch_transcript_lines(video_id: str) -> list[dict]:
    """Altyazıyı saniye damgasıyla çeker (TR tercih, yoksa mevcut ilk dil)."""
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

    errors: list[str] = []
    fetchers = (
        (_fetch_via_ytdlp, 28),
        (_fetch_via_invidious, 10),
        (_fetch_transcript_lines_inner, 8),
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


def _download_caption(base_url: str) -> list[dict]:
    url = base_url
    if "fmt=" not in url:
        url += ("&" if "?" in url else "?") + "fmt=json3"
    response = httpx.get(
        url,
        headers={"User-Agent": WATCH_UA, "Accept-Language": "tr-TR,tr;q=0.9"},
        timeout=18,
        follow_redirects=True,
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("Altyazı biçimi okunamadı.")
    return _lines_from_json3(data)


_VTT_STAMP = re.compile(
    r"(?:(\d+):)?(\d{2}):(\d{2})[\.,](\d{3})\s*-->"
)
INVIDIOUS_HOSTS = (
    "https://inv.nadeko.net",
    "https://invidious.privacyredirect.com",
    "https://iv.datura.network",
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


def _lines_from_caption_bytes(raw: bytes, ext: str) -> list[dict]:
    if not raw:
        return []
    kind = (ext or "").lower()
    if kind in {"json3", "json"}:
        data = json.loads(raw)
        if isinstance(data, dict):
            return _lines_from_json3(data)
        return []
    return _lines_from_vtt(raw.decode("utf-8", "replace"))


def _pick_ytdlp_track(info: dict) -> dict | None:
    bags = (info.get("subtitles") or {}, info.get("automatic_captions") or {})
    preferred = ("tr", "tr-TR", "en", "en-orig", "en-US")
    for bag in bags:
        for lang in preferred:
            tracks = bag.get(lang) or []
            json3 = next((item for item in tracks if item.get("ext") == "json3" and item.get("url")), None)
            if json3:
                return json3
            other = next(
                (
                    item
                    for item in tracks
                    if item.get("ext") in {"vtt", "srv3", "ttml"} and item.get("url")
                ),
                None,
            )
            if other:
                return other
    for bag in bags:
        for tracks in bag.values():
            json3 = next((item for item in tracks if item.get("ext") == "json3" and item.get("url")), None)
            if json3:
                return json3
    return None


def _fetch_via_ytdlp(video_id: str) -> list[dict]:
    import yt_dlp

    watch = f"https://www.youtube.com/watch?v={video_id}"
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
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


def _fetch_via_innertube(video_id: str) -> list[dict]:
    payload = {
        "context": {
            "client": {
                "clientName": "WEB",
                "clientVersion": "2.20240815.00.00",
                "hl": "tr",
                "gl": "TR",
            }
        },
        "videoId": video_id,
    }
    response = httpx.post(
        PLAYER_URL,
        json=payload,
        headers={"User-Agent": WATCH_UA, "Accept-Language": "tr-TR,tr;q=0.9"},
        timeout=18,
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
        raise ValueError("Bu video için altyazı bulunamadı.")
    return _download_caption(str(track["baseUrl"]))


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
